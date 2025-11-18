"""Unit tests for Agent Pool Manager.

Tests cover:
- Pool initialization with various configurations
- Agent allocation and status transitions
- Edge cases and error handling
- Pool statistics and monitoring
- Agent failure and recovery
"""

from unittest.mock import Mock, patch

import pytest

from src.agents.agent_pool import (
    DEFAULT_MAX_AGENTS,
    MAX_AGENTS_LIMIT,
    MIN_AGENTS,
    AgentPool,
    AgentStatus,
    ManagedAgent,
)

# Test constants
TEST_TOKEN = "test-token"  # noqa: S105
TEST_ORG_ID = "123"
TEST_ORG_ID_INT = 999
EXPECTED_ENUM_COUNT = 3
CUSTOM_POOL_SIZE = 5
SMALL_POOL_SIZE = 3
MEDIUM_POOL_SIZE = 7
DUAL_AGENT_POOL = 2
SINGLE_AGENT_POOL = 1
EXPECTED_CYCLE_LENGTH = 3


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
        assert len(statuses) == EXPECTED_ENUM_COUNT
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

        assert managed_agent.id == SINGLE_AGENT_POOL
        assert managed_agent.agent == mock_agent
        assert managed_agent.status == AgentStatus.BUSY
        assert managed_agent.current_task == "task-123"


class TestAgentPoolInitialization:
    """Tests for AgentPool initialization."""

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_default_size(self, mock_agent_class):
        """Test initializing pool with default size."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN)

        assert pool.org_id == TEST_ORG_ID
        assert pool.token == TEST_TOKEN
        assert pool.max_agents == DEFAULT_MAX_AGENTS
        assert len(pool.agents) == DEFAULT_MAX_AGENTS

        # Verify Agent was called with correct parameters
        assert mock_agent_class.call_count == DEFAULT_MAX_AGENTS
        mock_agent_class.assert_called_with(token=TEST_TOKEN, org_id=123)

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_custom_size(self, mock_agent_class):
        """Test initializing pool with custom size."""
        custom_size = 5
        pool = AgentPool(org_id="456", token=TEST_TOKEN, max_agents=custom_size)

        assert pool.max_agents == custom_size
        assert len(pool.agents) == custom_size
        assert mock_agent_class.call_count == custom_size

    def test_pool_initialization_minimum_size(self):
        """Test initializing pool with minimum size."""
        pool = AgentPool(org_id="789", token=TEST_TOKEN, max_agents=MIN_AGENTS)

        assert pool.max_agents == MIN_AGENTS
        assert len(pool.agents) == MIN_AGENTS

    def test_pool_initialization_maximum_size(self):
        """Test initializing pool with maximum size."""
        pool = AgentPool(
            org_id="999", token=TEST_TOKEN, max_agents=MAX_AGENTS_LIMIT,
        )

        assert pool.max_agents == MAX_AGENTS_LIMIT
        assert len(pool.agents) == MAX_AGENTS_LIMIT

    def test_pool_initialization_invalid_size_too_small(self):
        """Test that initializing with size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="must be between"):
            AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=0)

    def test_pool_initialization_invalid_size_too_large(self):
        """Test that initializing with size > 10 raises ValueError."""
        with pytest.raises(ValueError, match="must be between"):
            AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=11)

    def test_pool_initialization_invalid_size_negative(self):
        """Test that initializing with negative size raises ValueError."""
        with pytest.raises(ValueError, match="must be between"):
            AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=-1)


    def test_pool_initialization_invalid_org_id_non_numeric(self):
        """Test that initializing with non-numeric org_id raises ValueError."""
        with pytest.raises(ValueError, match="must be a valid integer string"):
            AgentPool(org_id="abc", token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

    def test_pool_initialization_invalid_org_id_empty(self):
        """Test that initializing with empty org_id raises ValueError."""
        with pytest.raises(ValueError, match="must be a valid integer string"):
            AgentPool(org_id="", token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

    def test_pool_initialization_invalid_org_id_float(self):
        """Test that initializing with float-like org_id works (converts to int)."""
        with pytest.raises(ValueError, match="must be a valid integer string"):
            AgentPool(org_id="123.45", token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

    @patch("src.agents.agent_pool.Agent")
    def test_pool_initialization_valid_org_id_string(self, mock_agent_class):
        """Test that valid numeric string org_id works correctly."""
        pool = AgentPool(org_id="999", token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)

        assert pool.org_id == "999"
        assert pool.org_id_int == TEST_ORG_ID_INT
        # Verify Agent was called with integer org_id
        mock_agent_class.assert_called_with(token=TEST_TOKEN, org_id=TEST_ORG_ID_INT)

    def test_all_agents_start_idle(self):
        """Test that all agents start with IDLE status."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

        for agent in pool.agents:
            assert agent.status == AgentStatus.IDLE
            assert agent.current_task is None

    def test_agents_have_sequential_ids(self):
        """Test that agents are assigned sequential IDs starting from 0."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

        for i, agent in enumerate(pool.agents):
            assert agent.id == i


class TestAgentAllocation:
    """Tests for agent allocation."""

    def test_get_idle_agent_when_available(self):
        """Test getting an idle agent when one is available."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.status == AgentStatus.IDLE
        assert isinstance(agent, ManagedAgent)

    def test_get_idle_agent_returns_first_idle(self):
        """Test that get_idle_agent returns the first idle agent."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

        # Mark first agent as busy
        pool.agents[0].status = AgentStatus.BUSY

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.id == SINGLE_AGENT_POOL  # Should return second agent

    def test_get_idle_agent_when_none_available(self):
        """Test getting an idle agent when none are available."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

        # Mark all agents as busy
        for agent in pool.agents:
            agent.status = AgentStatus.BUSY

        agent = pool.get_idle_agent()

        assert agent is None

    def test_get_idle_agent_skips_failed_agents(self):
        """Test that get_idle_agent skips failed agents."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

        # Mark first agent as failed
        pool.agents[0].status = AgentStatus.FAILED

        agent = pool.get_idle_agent()

        assert agent is not None
        assert agent.id != 0
        assert agent.status == AgentStatus.IDLE


class TestAgentStatusTransitions:
    """Tests for agent status transitions."""

    def test_mark_busy_from_idle(self):
        """Test marking an idle agent as busy."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]
        task_id = "task-123"

        pool.mark_busy(agent, task_id)

        assert agent.status == AgentStatus.BUSY
        assert agent.current_task == task_id

    def test_mark_busy_from_busy_raises_error(self):
        """Test that marking a busy agent as busy raises ValueError."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-1")

        with pytest.raises(ValueError, match=r"Cannot mark agent .* as busy"):
            pool.mark_busy(agent, "task-2")
        assert agent.current_task == "task-1"  # Should not change

    def test_mark_busy_from_failed_raises_error(self):
        """Test that marking a failed agent as busy raises ValueError."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]
        agent.status = AgentStatus.FAILED

        with pytest.raises(ValueError, match=r"Cannot mark agent .* as busy"):
            pool.mark_busy(agent, "task-1")

    def test_mark_idle_from_busy(self):
        """Test marking a busy agent as idle."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-123")
        pool.mark_idle(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    def test_mark_idle_from_failed(self):
        """Test marking a failed agent as idle (should work for cleanup)."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]
        agent.status = AgentStatus.FAILED

        pool.mark_idle(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    def test_mark_failed_from_busy(self):
        """Test marking a busy agent as failed."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-123")
        pool.mark_failed(agent, "Connection timeout")

        assert agent.status == AgentStatus.FAILED
        assert agent.current_task is None

    def test_mark_failed_from_idle(self):
        """Test marking an idle agent as failed."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_failed(agent)

        assert agent.status == AgentStatus.FAILED
        assert agent.current_task is None


class TestAgentRecovery:
    """Tests for agent failure handling and recovery."""

    def test_reset_agent_from_failed(self):
        """Test resetting a failed agent back to idle."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_failed(agent, "Test error")
        pool.reset_agent(agent)

        assert agent.status == AgentStatus.IDLE
        assert agent.current_task is None

    def test_reset_agent_from_idle_raises_error(self):
        """Test that resetting an idle agent raises ValueError."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        with pytest.raises(ValueError, match=r"Cannot reset agent .* current status is"):
            pool.reset_agent(agent)

    def test_reset_agent_from_busy_raises_error(self):
        """Test that resetting a busy agent raises ValueError."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_busy(agent, "task-1")

        with pytest.raises(ValueError, match=r"Cannot reset agent .* current status is"):
            pool.reset_agent(agent)


class TestPoolStatistics:
    """Tests for pool statistics and monitoring."""

    def test_get_stats_all_idle(self):
        """Test statistics when all agents are idle."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

        stats = pool.get_stats()

        assert stats["idle"] == CUSTOM_POOL_SIZE
        assert stats["busy"] == 0
        assert stats["failed"] == 0

    def test_get_stats_mixed_statuses(self):
        """Test statistics with mixed agent statuses."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=10)

        # Mark some agents as busy
        pool.mark_busy(pool.agents[0], "task-1")
        pool.mark_busy(pool.agents[1], "task-2")

        # Mark some agents as failed
        pool.mark_failed(pool.agents[2])

        stats = pool.get_stats()

        assert stats["idle"] == MEDIUM_POOL_SIZE
        assert stats["busy"] == DUAL_AGENT_POOL
        assert stats["failed"] == SINGLE_AGENT_POOL

    def test_get_stats_all_busy(self):
        """Test statistics when all agents are busy."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

        for i, agent in enumerate(pool.agents):
            pool.mark_busy(agent, f"task-{i}")

        stats = pool.get_stats()

        assert stats["idle"] == 0
        assert stats["busy"] == SMALL_POOL_SIZE
        assert stats["failed"] == 0

    def test_get_total_agents(self):
        """Test getting total agent count."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=MEDIUM_POOL_SIZE)

        assert pool.get_total_agents() == MEDIUM_POOL_SIZE


class TestConcurrentAllocation:
    """Tests for concurrent agent allocation scenarios."""

    def test_multiple_allocations(self):
        """Test allocating multiple agents sequentially."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=CUSTOM_POOL_SIZE)

        allocated_agents = []
        for i in range(3):
            agent = pool.get_idle_agent()
            assert agent is not None
            pool.mark_busy(agent, f"task-{i}")
            allocated_agents.append(agent)

        # Verify all allocated agents are unique
        agent_ids = [agent.id for agent in allocated_agents]
        assert len(set(agent_ids)) == SMALL_POOL_SIZE

        # Verify pool statistics
        stats = pool.get_stats()
        assert stats["busy"] == SMALL_POOL_SIZE
        assert stats["idle"] == DUAL_AGENT_POOL

    def test_allocate_all_agents(self):
        """Test allocating all agents in the pool."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SMALL_POOL_SIZE)

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
        assert stats["busy"] == SMALL_POOL_SIZE
        assert stats["idle"] == 0

    def test_release_and_reallocate(self):
        """Test releasing an agent and reallocating it."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)

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

    def test_mark_failed_with_error_message(self):
        """Test marking agent as failed with error message."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]
        error_msg = "Connection timeout after 30 seconds"

        pool.mark_failed(agent, error_msg)

        assert agent.status == AgentStatus.FAILED

    def test_mark_failed_without_error_message(self):
        """Test marking agent as failed without error message."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=DUAL_AGENT_POOL)
        agent = pool.agents[0]

        pool.mark_failed(agent)

        assert agent.status == AgentStatus.FAILED

    def test_single_agent_pool(self):
        """Test pool with single agent."""
        pool = AgentPool(org_id=TEST_ORG_ID, token=TEST_TOKEN, max_agents=SINGLE_AGENT_POOL)

        assert pool.get_total_agents() == SINGLE_AGENT_POOL
        agent = pool.get_idle_agent()
        assert agent is not None
        assert agent.id == 0

    @patch("src.agents.agent_pool.Agent")
    def test_org_id_conversion_to_int(self, mock_agent_class):
        """Test that org_id is converted to int when creating agents."""
        _pool = AgentPool(org_id="999", token=TEST_TOKEN, max_agents=SINGLE_AGENT_POOL)

        # Verify Agent was called with int org_id
        mock_agent_class.assert_called_with(token=TEST_TOKEN, org_id=TEST_ORG_ID_INT)
