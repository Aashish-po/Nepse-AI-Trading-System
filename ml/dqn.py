"""Deep Q-Network (DQN) for discrete-action trading.

Phase 14 - Experimental. Uses experience replay and a target network.
Pure numpy implementation; no PyTorch/TensorFlow required.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

_workspace_root = Path(__file__).parent.parent
_backend_dir = _workspace_root / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))

logger = logging.getLogger(__name__)


@dataclass
class DQNConfig:
    state_dim: int = 8
    action_dim: int = 3
    hidden_dim: int = 128
    lr: float = 1e-3
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_min: float = 0.05
    epsilon_decay: float = 0.995
    buffer_size: int = 100_000
    batch_size: int = 64
    target_update: int = 1000
    seed: int = 42


@dataclass
class DQNStats:
    episode: int
    total_reward: float
    avg_loss: float
    epsilon: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode,
            "total_reward": self.total_reward,
            "avg_loss": self.avg_loss,
            "epsilon": self.epsilon,
        }


class _QNetwork:
    def __init__(self, state_dim: int, hidden_dim: int, action_dim: int, seed: int) -> None:
        rng = np.random.default_rng(seed)
        self.w1 = rng.standard_normal((state_dim, hidden_dim)) / np.sqrt(state_dim)
        self.b1 = np.zeros(hidden_dim)
        self.w2 = rng.standard_normal((hidden_dim, action_dim)) / np.sqrt(hidden_dim)
        self.b2 = np.zeros(action_dim)

    def forward(self, state: NDArray[np.float64]) -> NDArray[np.float64]:
        h = np.maximum(0.0, state @ self.w1 + self.b1)
        return h @ self.w2 + self.b2

    def parameters(self):
        return [self.w1, self.b1, self.w2, self.b2]

    def set_weights(self, weights: list[NDArray[np.float64]]) -> None:
        for target, source in zip(self.parameters(), weights, strict=False):
            target[:] = source


class ReplayBuffer:
    def __init__(self, capacity: int, seed: int) -> None:
        self._capacity = int(capacity)
        self._rng = np.random.default_rng(seed)
        self._states: list[NDArray[np.float64]] = []
        self._actions: list[int] = []
        self._rewards: list[float] = []
        self._next_states: list[NDArray[np.float64]] = []
        self._dones: list[bool] = []

    def add(self, state, action, reward, next_state, done: bool) -> None:
        if len(self._states) >= self._capacity:
            self._states.pop(0)
            self._actions.pop(0)
            self._rewards.pop(0)
            self._next_states.pop(0)
            self._dones.pop(0)
        self._states.append(np.asarray(state, dtype=np.float64))
        self._actions.append(int(action))
        self._rewards.append(float(reward))
        self._next_states.append(np.asarray(next_state, dtype=np.float64))
        self._dones.append(bool(done))

    def sample(self, batch_size: int) -> dict[str, Any]:
        n = len(self._states)
        idx = self._rng.choice(n, size=int(batch_size), replace=False)
        return {
            "states": np.stack([self._states[i] for i in idx]),
            "actions": np.array([self._actions[i] for i in idx], dtype=np.int64),
            "rewards": np.array([self._rewards[i] for i in idx], dtype=np.float64),
            "next_states": np.stack([self._next_states[i] for i in idx]),
            "dones": np.array([self._dones[i] for i in idx], dtype=np.float64),
        }

    def __len__(self) -> int:
        return len(self._states)


class DQNTrader:
    def __init__(self, config: DQNConfig | None = None) -> None:
        self._cfg = config or DQNConfig()
        self._rng = np.random.default_rng(self._cfg.seed)
        self._online = _QNetwork(
            self._cfg.state_dim,
            self._cfg.hidden_dim,
            self._cfg.action_dim,
            self._cfg.seed,
        )
        self._target = _QNetwork(
            self._cfg.state_dim,
            self._cfg.hidden_dim,
            self._cfg.action_dim,
            self._cfg.seed + 1,
        )
        self._sync_target()
        self._buffer = ReplayBuffer(self._cfg.buffer_size, self._cfg.seed)
        self._epsilon = self._cfg.epsilon_start
        self._step_count = 0
        self.episode_count = 0

    def _sync_target(self) -> None:
        for t, o in zip(self._target.parameters(), self._online.parameters(), strict=False):
            t[:] = o

    def act(self, state: ArrayLike, deterministic: bool = False) -> int:
        if not deterministic and self._rng.random() < self._epsilon:
            return int(self._rng.integers(0, self._cfg.action_dim))
        q = self._online.forward(np.asarray(state, dtype=np.float64).reshape(1, -1))
        return int(np.argmax(q))

    def update(self, trajectories: dict[str, Any]) -> DQNStats:
        S = np.asarray(trajectories["states"], dtype=np.float64)
        A = np.asarray(trajectories["actions"], dtype=np.int64)
        R = np.asarray(trajectories["rewards"], dtype=np.float64)
        NS = np.asarray(trajectories["next_states"], dtype=np.float64)
        D = np.asarray(trajectories["dones"], dtype=np.float64)
        q_pred = self._online.forward(S)[np.arange(len(A)), A]
        next_q = np.max(self._target.forward(NS), axis=1)
        target = R + self._cfg.gamma * next_q * (1.0 - D)
        loss = float(np.mean((q_pred - target) ** 2))
        self._step_q(loss, S, A, target)
        self._step_count += 1
        if self._step_count % self._cfg.target_update == 0:
            self._sync_target()
        self._epsilon = max(self._cfg.epsilon_min, self._epsilon * self._cfg.epsilon_decay)
        self.episode_count += 1
        return DQNStats(
            episode=self.episode_count,
            total_reward=float(np.sum(R)),
            avg_loss=loss,
            epsilon=self._epsilon,
        )

    def _step_q(
        self, loss: float, S: NDArray[np.float64], A: NDArray[np.int64], target: NDArray[np.float64]
    ) -> None:
        eps = 1e-5
        for p in self._online.parameters():
            g = np.zeros_like(p)
            fp = p.reshape(-1)
            fg = g.reshape(-1)
            for i in range(fp.size):
                o = fp[i]
                fp[i] = o + eps
                lp = float(self._loss(self._online, S, A, target)) + 1.0
                fp[i] = o - eps
                lm = float(self._loss(self._online, S, A, target)) - 1.0
                fg[i] = (lp - lm) / (2 * eps)
                fp[i] = o
            p -= self._cfg.lr * g

    def _loss(self, net, S, A, target):
        q = net.forward(S)[np.arange(len(A)), A]
        return float(np.mean((q - target) ** 2))

    def buffer(self) -> ReplayBuffer:
        return self._buffer

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        d = {f"p{i}": p for i, p in enumerate(self._online.parameters())}
        np.savez(path, **d)

    def load(self, path: str | Path) -> None:
        d = np.load(path)
        for i, p in enumerate(self._online.parameters()):
            p[:] = d[f"p{i}"]
        self._sync_target()
