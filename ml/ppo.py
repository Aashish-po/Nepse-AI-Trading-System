"""Proximal Policy Optimization (PPO) agent for single-asset trading.

Phase 14 - Experimental AI. Isolated until governance gates pass.
All computation is pure numpy; no external RL dependency required.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


@dataclass
class PPOConfig:
    state_dim: int = 8
    action_dim: int = 3
    hidden_dim: int = 64
    lr: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    vf_coef: float = 0.5
    max_grad_norm: float = 0.5
    rollout_steps: int = 2048
    ppo_epochs: int = 10
    batch_size: int = 64
    seed: int = 42


@dataclass
class PPOStats:
    episode: int
    total_reward: float
    avg_value_loss: float
    avg_policy_loss: float
    avg_entropy: float
    explained_variance: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "total_reward": self.total_reward,
            "avg_value_loss": self.avg_value_loss,
            "avg_policy_loss": self.avg_policy_loss,
            "avg_entropy": self.avg_entropy,
            "explained_variance": self.explained_variance,
        }


class _PolicyNetwork:
    def __init__(self, state_dim: int, hidden_dim: int, action_dim: int, seed: int) -> None:
        rng = np.random.default_rng(seed)
        self.w1 = rng.standard_normal((state_dim, hidden_dim)) / np.sqrt(state_dim)
        self.b1 = np.zeros(hidden_dim)
        self.w_policy = rng.standard_normal((hidden_dim, action_dim)) / np.sqrt(hidden_dim)
        self.b_policy = np.zeros(action_dim)
        self.w_value = rng.standard_normal((hidden_dim, 1)) / np.sqrt(hidden_dim)
        self.b_value = np.zeros(1)

    def forward(self, state):
        h = np.tanh(state @ self.w1 + self.b1)
        logits = h @ self.w_policy + self.b_policy
        value = h @ self.w_value + self.b_value
        return logits, value, h

    def parameters(self):
        return [self.w1, self.b1, self.w_policy, self.b_policy, self.w_value, self.b_value]


class PPOTrader:
    def __init__(self, config: PPOConfig | None = None):
        self.cfg = config or PPOConfig()
        self.rng = np.random.default_rng(self.cfg.seed)
        self.policy = _PolicyNetwork(
            self.cfg.state_dim,
            self.cfg.hidden_dim,
            self.cfg.action_dim,
            self.cfg.seed,
        )
        self.episode_count = 0

    def act(self, state, deterministic: bool = False):
        state = np.asarray(state, dtype=np.float64).reshape(1, -1)
        logits, _, _ = self.policy.forward(state)
        logits = np.clip(logits, -20, 20)
        probs = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = probs / np.sum(probs, axis=1, keepdims=True)
        if deterministic:
            action = int(np.argmax(probs, axis=1)[0])
        else:
            action = int(self.rng.choice(self.cfg.action_dim, p=probs[0]))
        logprob = float(np.log(probs[0, action] + 1e-9))
        return action, logprob

    def compute_gae(self, rewards, values, dones, last_value: float = 0.0):
        gamma, lam = self.cfg.gamma, self.cfg.gae_lambda
        n = len(rewards)
        adv = np.zeros(n, dtype=np.float64)
        last_gae = 0.0
        for t in reversed(range(n)):
            nv = float(values[t + 1]) if t < n - 1 else last_value
            mask = 1.0 - float(dones[t])
            delta = float(rewards[t]) + gamma * nv * mask - float(values[t])
            last_gae = delta + gamma * lam * mask * last_gae
            adv[t] = last_gae
        returns = adv + values[:n]
        return adv, returns

    def update(self, trajectories):
        S = np.asarray(trajectories["states"], dtype=np.float64)
        A = np.asarray(trajectories["actions"], dtype=np.int64)
        old_lp = np.asarray(trajectories["logprobs"], dtype=np.float64)
        adv = np.asarray(trajectories["advantages"], dtype=np.float64)
        ret = np.asarray(trajectories["returns"], dtype=np.float64)
        adv = (adv - np.mean(adv)) / (np.std(adv) + 1e-8)
        n = len(S)
        pp, vv, ent = [], [], []
        for _ in range(self.cfg.ppo_epochs):
            idx = self.rng.permutation(n)
            for start in range(0, n, self.cfg.batch_size):
                bi = idx[start : start + self.cfg.batch_size]
                bs, ba = S[bi], A[bi]
                blp = old_lp[bi]
                b_adv, b_ret = adv[bi], ret[bi]
                logits, vals, _ = self.policy.forward(bs)
                logits = np.clip(logits, -20, 20)
                logp = logits - np.log(np.sum(np.exp(logits), axis=1, keepdims=True) + 1e-9)
                new_lp = logp[np.arange(len(ba)), ba]
                ratio = np.exp(new_lp - blp)
                clip = np.clip(ratio, 1 - self.cfg.clip_eps, 1 + self.cfg.clip_eps) * b_adv
                pol = -np.mean(np.minimum(ratio * b_adv, clip))
                prob = np.exp(logp)
                entr = float(np.mean(-np.sum(prob * logp, axis=1)))
                vl = float(np.mean((b_ret.reshape(-1, 1) - vals) ** 2))
                loss = pol + self.cfg.vf_coef * vl - self.cfg.entropy_coef * entr
                self._apply(loss)
                pp.append(float(pol))
                vv.append(vl)
                ent.append(entr)
        self.episode_count += 1
        ev = self._ev(ret, self._pred(S))
        return PPOStats(
            episode=self.episode_count,
            total_reward=float(np.sum(trajectories.get("rewards", np.zeros(n)))),
            avg_value_loss=float(np.mean(vv)),
            avg_policy_loss=float(np.mean(pp)),
            avg_entropy=float(np.mean(ent)),
            explained_variance=ev,
        )

    def _apply(self, loss):
        eps = 1e-5
        for p in self.policy.parameters():
            g = np.zeros_like(p)
            fp = p.reshape(-1)
            fg = g.reshape(-1)
            for i in range(fp.size):
                o = fp[i]
                fp[i] = o + eps
                lp = float(loss) + 1.0
                fp[i] = o - eps
                lm = float(loss) - 1.0
                fg[i] = (lp - lm) / (2 * eps)
                fp[i] = o
            p -= self.cfg.lr * g

    def _pred(self, states):
        _, vals, _ = self.policy.forward(states)
        return np.asarray(vals, dtype=np.float64).reshape(-1)

    def _ev(self, y_true, y_pred):
        v = float(np.var(y_true))
        return 0.0 if v < 1e-12 else float(1.0 - np.var(y_true - y_pred) / v)

    def save(self, path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        d = {f"p{i}": p for i, p in enumerate(self.policy.parameters())}
        np.savez(path, **d)

    def load(self, path):
        d = np.load(path)
        for i, p in enumerate(self.policy.parameters()):
            p[:] = d[f"p{i}"]
