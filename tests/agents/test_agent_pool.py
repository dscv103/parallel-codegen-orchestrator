"""Unit tests for Agent Pool Manager.

Tests cover:
- Pool initialization with various configurations
- Agent allocation and status transitions
- Edge cases and error handling
- Pool statistics and monitoring
- Agent failure and recovery
"""

import pytest
from unittest.mock import Mock, patch

from src.agents.agent_pool import (
    AgentPool,
    AgentStatus,
    ManagedAgent,
    DEFAULT_MAX_AGENTS,
    MIN_AGENTS,
    MAX_AGENTS_LIMIT,
)


class TestAgentStatus:
    """Tests for AgentStatus enum."""

    def test_agent_status_values(self):
        """Test that AgentStatus has correct values."""
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.FAILED.value == "failed"

    def test_agent_status_enum_members(self):
        """Test that all enum members exist."""
        statuses = list(AgentStatus)
        assert len(statuses) == 3
        assert AgentStatus.IDLE in statuses
        assert AgentStatus.BUSY in statuses
        assert AgentStatus.FAILED in statuses


class TestManagedAgent:
    """Tests for ManagedAgent dataclass."""

    def test_managed_agent_creation(self):
        """Test creating a ManagedAgent with required fields."""
        mock_agent = Mock()
        managed_agent = ManagedAgent(id=0, agent=mock_agent)

        assert managed_agent.id == 0
        assert managed_agent.agent == mock_agent
        assert managed_agent.status == AgentStatus.IDLE
        assert managed_agent.current_task is None

    def test_managed_agent_with_all_fields(self):
        """Test creating a ManagedAgent with all fields."""
        mock_agent = Mock()
        managed_agent = ManagedAgent(
            id=1,
            agent=mock_agent,
            status=AgentStatus.BUSY,
            current_task="task-123",
        )

        assert managed_agent.id == 1
        assert managed_agent.agent == mock_agent
        assert managed_agent.status == AgentStatus.BUSY
        assert managed_agent.current_task == "task-123"


class TestAgentPoolInitialization:
    """Tests for AgentPool initialization."""

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_default_size(self, mock_agent_class):
        """Test initializing pool with default size."""
        pool = AgentPool(org_id="123", token="test-token")

        assert pool.org_id == "123"
        assert pool.token == "test-token"
        assert pool.max_agents == DEFAULT_MAX_AGENTS
        assert len(pool.agents) == DEFAULT_MAX_AGENTS

        # Verify Agent was called with correct parameters
        assert mock_agent_class.call_count == DEFAULT_MAX_AGENTS
        mock_agent_class.assert_called_with(token="test-token", org_id=123)

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_custom_size(self, mock_agent_class):
        """Test initializing pool with custom size."""
        custom_size = 5
        pool = AgentPool(org_id="456", token="test-token", max_agents=custom_size)

        assert pool.max_agents == custom_size
        assert len(pool.agents) == custom_size
        assert mock_agent_class.call_count == custom_size

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_minimum_size(self, mock_agent_class):
        """Test initializing pool with minimum size."""
        pool = AgentPool(org_id="789", token="test-token", max_agents=MIN_AGENTS)

        assert pool.max_agents == MIN_AGENTS
        assert len(pool.agents) == MIN_AGENTS

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_maximum_size(self, mock_agent_class):
        """Test initializing pool with maximum size."""
        pool = AgentPool(
            org_id="999", token="test-token", max_agents=MAX_AGENTS_LIMIT
        )

        assert pool.max_agents == MAX_AGENTS_LIMIT
        assert len(pool.agents) == MAX_AGENTS_LIMIT

    def test_pool_initialization_invalid_size_too_small(self):
        """Test that initializing with size < 1 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="123", token="test-token", max_agents=0)

        assert "must be between" in str(exc_info.value)

    def test_pool_initialization_invalid_size_too_large(self):
        """Test that initializing with size > 10 raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="123", token="test-token", max_agents=11)

        assert "must be between" in str(exc_info.value)

    def test_pool_initialization_invalid_size_negative(self):
        """Test that initializing with negative size raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="123", token="test-token", max_agents=-1)

        assert "must be between" in str(exc_info.value)

    def test_pool_initialization_invalid_org_id_non_numeric(self):
        """Test that initializing with non-numeric org_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="abc", token="test-token", max_agents=5)

        assert "must be a valid integer string" in str(exc_info.value)
        assert "abc" in str(exc_info.value)

    def test_pool_initialization_invalid_org_id_empty(self):
        """Test that initializing with empty org_id raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="", token="test-token", max_agents=5)

        assert "must be a valid integer string" in str(exc_info.value)

    def test_pool_initialization_invalid_org_id_float(self):
        """Test that initializing with float-like org_id works (converts to int)."""
        with pytest.raises(ValueError) as exc_info:
            AgentPool(org_id="123.45", token="test-token", max_agents=5)

        assert "must be a valid integer string" in str(exc_info.value)

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_valid_org_id_string(self, mock_agent_class):
        """Test that valid numeric string org_id works correctly."""
        pool = AgentPool(org_id="999", token="test-token", max_agents=2)

        assert pool.org_id == "999"
        assert pool.org_id_int == 999
        # Verify Agent was called with integer org_id
        mock_agent_class.assert_called_with(token="test-token", org_id=999)

    @patch("src.agents.agent_pool.Agent")
    def test_all_agents_start_idle(self, mock_agent_class):
        """Test that all agents start with IDLE status."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=5)

        for agent in pool.agents:
            assert agent.status == AgentStatus.IDLE
            assert agent.current_task is None

    @patch("src.agents.agent_pool.Agent")
    def test_agents_have_sequential_ids(self, mock_agent_class):
        """Test that agents are assigned sequential IDs starting from 0."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=5)

        for i, agent in enumerate(pool.agents):
            assert agent.id == i


class TestAgentAllocation:
    """Tests for agent allocation."""

    @patch("src.agents.agent_pool.Agent")
    def test_get_idle_agent_when_available(self, mock_agent_class):
        """Test getting an idle agent when one is available."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.status == AgentStatus.IDLE
        assert isinstance(agent, ManagedAgent)

    @patch("src.agents.agent_pool.Agent")
    def test_get_idle_agent_returns_first_idle(self, mock_agent_class):
        """Test that get_idle_agent returns the first idle agent."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        # Mark first agent as busy
        pool.agents[0].status = AgentStatus.BUSY

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.id == 1  # Should return second agent

    @patch("src.agents.agent_pool.Agent")
    def test_get_idle_agent_when_none_available(self, mock_agent_class):
        """Test getting an idle agent when none are available."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        # Mark all agents as busy
        for agent in pool.agents:
            agent.status = AgentStatus.BUSY

        agent = pool.get_idle_agent()

        assert agent is None

    @patch("src.agents.agent_pool.Agent")
    def test_get_idle_agent_skips_failed_agents(self, mock_agent_class):
        """Test that get_idle_agent skips failed agents."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        # Mark first agent as failed
        pool.agents[0].status = AgentStatus.FAILED

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.id != 0
        assert agent.status == AgentStatus.IDLE


class TestAgentStatusTransitions:
    """Tests for agent status transitions."""

    @patch("src.agents.agent_pool.Agent")
    def test_mark_busy_from_idle(self, mock_agent_class):
        """Test marking an idle agent as busy."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]
        task_id = "task-123"

        pool.mark_busy(agent, task_id)

        assert agent.status == AgentStatus.BUSY
        assert agent.current_task == task_id

    @patch("src.agents.agent_pool.Agent")
    def test_mark_busy_from_busy_raises_error(self, mock_agent_class):
        """Test that marking a busy agent as busy raises ValueError."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-1")

        with pytest.raises(ValueError) as exc_info:
            pool.mark_busy(agent, "task-2")

        assert "Cannot mark agent" in str(exc_info.value)
        assert agent.current_task == "task-1"  # Should not change

    @patch("src.agents.agent_pool.Agent")
    def test_mark_busy_from_failed_raises_error(self, mock_agent_class):
        """Test that marking a failed agent as busy raises ValueError."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]
        agent.status = AgentStatus.FAILED

        with pytest.raises(ValueError) as exc_info:
            pool.mark_busy(agent, "task-1")

        assert "Cannot mark agent" in str(exc_info.value)

    @patch("src.agents.agent_pool.Agent")
    def test_mark_idle_from_busy(self, mock_agent_class):
        """Test marking a busy agent as idle."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-123")
        pool.mark_idle(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    @patch("src.agents.agent_pool.Agent")
    def test_mark_idle_from_failed(self, mock_agent_class):
        """Test marking a failed agent as idle (should work for cleanup)."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]
        agent.status = AgentStatus.FAILED

        pool.mark_idle(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    @patch("src.agents.agent_pool.Agent")
    def test_mark_failed_from_busy(self, mock_agent_class):
        """Test marking a busy agent as failed."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-123")
        pool.mark_failed(agent, "Connection timeout")

        assert agent.status == AgentStatus.FAILED
        assert agent.current_task is None

    @patch("src.agents.agent_pool.Agent")
    def test_mark_failed_from_idle(self, mock_agent_class):
        """Test marking an idle agent as failed."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_failed(agent)

        assert agent.status == AgentStatus.FAILED
        assert agent.current_task is None


class TestAgentRecovery:
    """Tests for agent failure handling and recovery."""

    @patch("src.agents.agent_pool.Agent")
    def test_reset_agent_from_failed(self, mock_agent_class):
        """Test resetting a failed agent back to idle."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_failed(agent, "Test error")
        pool.reset_agent(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    @patch("src.agents.agent_pool.Agent")
    def test_reset_agent_from_idle_raises_error(self, mock_agent_class):
        """Test that resetting an idle agent raises ValueError."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        with pytest.raises(ValueError) as exc_info:
            pool.reset_agent(agent)

        assert "Cannot reset agent" in str(exc_info.value)
        assert "expected FAILED" in str(exc_info.value)

    @patch("src.agents.agent_pool.Agent")
    def test_reset_agent_from_busy_raises_error(self, mock_agent_class):
        """Test that resetting a busy agent raises ValueError."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-1")

        with pytest.raises(ValueError) as exc_info:
            pool.reset_agent(agent)

        assert "Cannot reset agent" in str(exc_info.value)


class TestPoolStatistics:
    """Tests for pool statistics and monitoring."""

    @patch("src.agents.agent_pool.Agent")
    def test_get_stats_all_idle(self, mock_agent_class):
        """Test statistics when all agents are idle."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=5)

        stats = pool.get_stats()

        assert stats["idle"] == 5
        assert stats["busy"] == 0
        assert stats["failed"] == 0

    @patch("src.agents.agent_pool.Agent")
    def test_get_stats_mixed_statuses(self, mock_agent_class):
        """Test statistics with mixed agent statuses."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=10)

        # Mark some agents as busy
        pool.mark_busy(pool.agents[0], "task-1")
        pool.mark_busy(pool.agents[1], "task-2")

        # Mark some agents as failed
        pool.mark_failed(pool.agents[2])

        stats = pool.get_stats()

        assert stats["idle"] == 7
        assert stats["busy"] == 2
        assert stats["failed"] == 1

    @patch("src.agents.agent_pool.Agent")
    def test_get_stats_all_busy(self, mock_agent_class):
        """Test statistics when all agents are busy."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        for i, agent in enumerate(pool.agents):
            pool.mark_busy(agent, f"task-{i}")

        stats = pool.get_stats()

        assert stats["idle"] == 0
        assert stats["busy"] == 3
        assert stats["failed"] == 0

    @patch("src.agents.agent_pool.Agent")
    def test_get_total_agents(self, mock_agent_class):
        """Test getting total agent count."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=7)

        assert pool.get_total_agents() == 7


class TestConcurrentAllocation:
    """Tests for concurrent agent allocation scenarios."""

    @patch("src.agents.agent_pool.Agent")
    def test_multiple_allocations(self, mock_agent_class):
        """Test allocating multiple agents sequentially."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=5)

        allocated_agents = []
        for i in range(3):
            agent = pool.get_idle_agent()
            assert agent is not None
            pool.mark_busy(agent, f"task-{i}")
            allocated_agents.append(agent)

        # Verify all allocated agents are unique
        agent_ids = [agent.id for agent in allocated_agents]
        assert len(set(agent_ids)) == 3

        # Verify pool statistics
        stats = pool.get_stats()
        assert stats["busy"] == 3
        assert stats["idle"] == 2

    @patch("src.agents.agent_pool.Agent")
    def test_allocate_all_agents(self, mock_agent_class):
        """Test allocating all agents in the pool."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=3)

        # Allocate all agents
        for i in range(3):
            agent = pool.get_idle_agent()
            assert agent is not None
            pool.mark_busy(agent, f"task-{i}")

        # Try to allocate one more
        agent = pool.get_idle_agent()
        assert agent is None

        # Verify all agents are busy
        stats = pool.get_stats()
        assert stats["busy"] == 3
        assert stats["idle"] == 0

    @patch("src.agents.agent_pool.Agent")
    def test_release_and_reallocate(self, mock_agent_class):
        """Test releasing an agent and reallocating it."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)

        # Allocate both agents
        agent1 = pool.get_idle_agent()
        pool.mark_busy(agent1, "task-1")

        agent2 = pool.get_idle_agent()
        pool.mark_busy(agent2, "task-2")

        # No agents available
        assert pool.get_idle_agent() is None

        # Release one agent
        pool.mark_idle(agent1)

        # Should be able to allocate again
        agent3 = pool.get_idle_agent()
        assert agent3 is not None
        assert agent3.id == agent1.id  # Should get the same agent


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @patch("src.agents.agent_pool.Agent")
    def test_mark_failed_with_error_message(self, mock_agent_class):
        """Test marking agent as failed with error message."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]
        error_msg = "Connection timeout after 30 seconds"

        pool.mark_failed(agent, error_msg)

        assert agent.status == AgentStatus.FAILED

    @patch("src.agents.agent_pool.Agent")
    def test_mark_failed_without_error_message(self, mock_agent_class):
        """Test marking agent as failed without error message."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=2)
        agent = pool.agents[0]

        pool.mark_failed(agent)

        assert agent.status == AgentStatus.FAILED

    @patch("src.agents.agent_pool.Agent")
    def test_single_agent_pool(self, mock_agent_class):
        """Test pool with single agent."""
        pool = AgentPool(org_id="123", token="test-token", max_agents=1)

        assert pool.get_total_agents() == 1
        agent = pool.get_idle_agent()
        assert agent is not None
        assert agent.id == 0

    @patch("src.agents.agent_pool.Agent")
    def test_org_id_conversion_to_int(self, mock_agent_class):
        """Test that org_id is converted to int when creating agents."""
        pool = AgentPool(org_id="999", token="test-token", max_agents=1)

        # Verify Agent was called with int org_id
        mock_agent_class.assert_called_with(token="test-token", org_id=999)
