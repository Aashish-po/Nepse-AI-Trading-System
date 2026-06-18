"""Tests for Phase 14: Experimental AI (PPO, DQN, GNN, Ensembles)."""

from __future__ import annotations

import numpy as np

from ml.dqn import DQNConfig, DQNStats, DQNTrader, ReplayBuffer
from ml.ensemble import EnsembleBuilder, EnsembleConfig
from ml.gnn import (
    GNNConfig,
    GNNStats,
    GraphTradingGNN,
    build_correlation_adjacency,
)
from ml.ppo import PPOConfig, PPOStats, PPOTrader


class TestPPO:
    def test_act_returns_valid_action(self):
        agent = PPOTrader(PPOConfig(state_dim=6, action_dim=3, seed=0))
        action, logprob = agent.act([0.1, -0.2, 0.0, 0.1, -0.3, 0.2])
        assert action in {0, 1, 2}
        assert -10.0 <= logprob <= 0.0

    def test_deterministic_action_is_stable(self):
        agent = PPOTrader(PPOConfig(state_dim=4, action_dim=3, seed=1))
        state = [0.1, -0.2, 0.0, 0.1]
        a1, _ = agent.act(state, deterministic=True)
        a2, _ = agent.act(state, deterministic=True)
        assert a1 == a2

    def test_gae_shapes(self):
        agent = PPOTrader(PPOConfig(state_dim=4, seed=2))
        rewards = np.ones(10, dtype=np.float64)
        values = np.ones(11, dtype=np.float64)
        dones = np.zeros(10, dtype=np.float64)
        adv, ret = agent.compute_gae(rewards, values, dones)
        assert adv.shape == (10,)
        assert ret.shape == (10,)

    def test_update_returns_stats(self):
        agent = PPOTrader(PPOConfig(state_dim=4, action_dim=3, seed=3))
        traj = {
            "states": np.random.default_rng(4).standard_normal((8, 4)),
            "actions": np.array([0, 1, 2, 0, 1, 2, 0, 1]),
            "logprobs": np.zeros(8, dtype=np.float64),
            "advantages": np.ones(8, dtype=np.float64),
            "returns": np.ones(8, dtype=np.float64),
            "rewards": np.ones(8, dtype=np.float64),
        }
        stats = agent.update(traj)
        assert isinstance(stats, PPOStats)
        assert stats.episode == 1


class TestDQN:
    def test_act_exploration(self):
        agent = DQNTrader(DQNConfig(state_dim=4, action_dim=3, epsilon_start=1.0, seed=0))
        actions = [agent.act([0.1, -0.2, 0.0, 0.1]) for _ in range(50)]
        assert all(a in {0, 1, 2} for a in actions)

    def test_deterministic_policy(self):
        agent = DQNTrader(DQNConfig(state_dim=4, action_dim=3, epsilon_start=0.0, seed=1))
        state = [0.1, -0.2, 0.0, 0.1]
        a1 = agent.act(state, deterministic=True)
        a2 = agent.act(state, deterministic=True)
        assert a1 == a2

    def test_buffer_add_and_sample(self):
        buf = ReplayBuffer(capacity=100, seed=0)
        for i in range(20):
            buf.add([float(i)], i % 3, 1.0, [float(i + 1)], False)
        assert len(buf) == 20
        batch = buf.sample(5)
        assert batch["states"].shape == (5, 1)

    def test_update_returns_stats(self):
        agent = DQNTrader(DQNConfig(state_dim=4, action_dim=3, seed=2))
        rng = np.random.default_rng(3)
        traj = {
            "states": rng.standard_normal((16, 4)),
            "actions": rng.integers(0, 3, size=16),
            "rewards": rng.standard_normal(16),
            "next_states": rng.standard_normal((16, 4)),
            "dones": np.zeros(16, dtype=np.float64),
        }
        stats = agent.update(traj)
        assert isinstance(stats, DQNStats)
        assert stats.episode == 1


class TestGNN:
    def test_adjacency_2d(self):
        ret = np.random.default_rng(0).standard_normal((50, 4))
        adj = build_correlation_adjacency(ret, threshold=0.2)
        assert adj.shape == (4, 4)
        assert np.allclose(adj.diagonal(), 1.0)

    def test_adjacency_1d(self):
        ret = np.array([0.1, -0.2, 0.3])
        adj = build_correlation_adjacency(ret)
        assert adj.shape == (3, 3)

    def test_forward_output_shape(self):
        gnn = GraphTradingGNN(GNNConfig(n_nodes=4, node_features=8, output_dim=3))
        x = np.random.default_rng(1).standard_normal((4, 8))
        adj = np.eye(4)
        out = gnn.forward(x, adj)
        assert out.shape == (4, 3)

    def test_fit_step_returns_stats(self):
        gnn = GraphTradingGNN(GNNConfig(n_nodes=2, node_features=4, output_dim=3, seed=7))
        x = np.random.default_rng(7).standard_normal((2, 4))
        adj = np.array([[0.8, 0.2], [0.2, 0.8]])
        labels = np.array([0, 1])
        stats = gnn.fit_step(x, adj, labels)
        assert isinstance(stats, GNNStats)
        assert stats.epoch == 1

    def test_predict_valid_actions(self):
        gnn = GraphTradingGNN(GNNConfig())
        x = np.random.default_rng(8).standard_normal((2, 8))
        adj = np.eye(2)
        preds = gnn.predict(x, adj)
        assert set(preds.tolist()) <= {0, 1, 2}


class TestEnsemble:
    def _make_models(self):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        rng = np.random.default_rng(9)
        X = rng.standard_normal((40, 4))
        y = (X[:, 0] > 0).astype(int)
        lr = LogisticRegression(max_iter=200).fit(X, y)
        rf = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
        return lr, rf

    def test_weighted_ensemble(self):
        lr, rf = self._make_models()
        builder = EnsembleBuilder(EnsembleConfig(method="weighted", weights=[0.6, 0.4]))
        builder.add_model(lr, 0.6)
        builder.add_model(rf, 0.4)
        rng = np.random.default_rng(10)
        X = rng.standard_normal((20, 4))
        y = (X[:, 0] > 0).astype(int)
        ensemble = builder.fit(X, y)
        assert ensemble.metrics["n_models"] == 2
        preds = builder.predict(X)
        assert preds.shape == (20, 2)

    def test_default_weights(self):
        lr, rf = self._make_models()
        builder = EnsembleBuilder(EnsembleConfig())
        builder.add_model(lr)
        builder.add_model(rf)
        rng = np.random.default_rng(11)
        X = rng.standard_normal((20, 4))
        y = (X[:, 0] > 0).astype(int)
        builder.fit(X, y)
        preds = builder.predict(X)
        assert preds.shape == (20, 2)
