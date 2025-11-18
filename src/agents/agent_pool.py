"""Agent Pool Manager for Codegen agents.

This module implements the agent pool manager that maintains and allocates
Codegen agents for concurrent task execution. The pool tracks agent status
(IDLE, BUSY, FAILED) and provides methods for allocation and lifecycle management.
"""

from dataclasses import dataclass, field
from enum import Enum

import structlog
from codegen import Agent

# Initialize logger
logger = structlog.get_logger()

# Constants
DEFAULT_MAX_AGENTS = 10
MIN_AGENTS = 1
MAX_AGENTS_LIMIT = 10


class AgentStatus(Enum):
    """Agent status enumeration.

    Represents the current state of a managed agent in the pool.
    """

    IDLE = "idle"
    BUSY = "busy"
    FAILED = "failed"


@dataclass
class ManagedAgent:
    """Managed agent wrapper with status tracking.

    Wraps a Codegen Agent instance with additional metadata for
    pool management including status and current task assignment.

    Attributes:
        id: Unique identifier for the agent (0-based index)
        agent: The Codegen Agent instance
        status: Current status (IDLE, BUSY, or FAILED)
        current_task: ID of the currently assigned task (None if idle)
    """

    id: int
    agent: Agent
    status: AgentStatus = field(default=AgentStatus.IDLE)
    current_task: str | None = None


class AgentPool:
    """Agent pool manager for Codegen agents.

    Manages a pool of Codegen agents with configurable size (max 10).
    Tracks agent status and provides methods for allocation, status
    management, and pool statistics.

    The pool supports:
    - Agent allocation (get_idle_agent)
    - Status transitions (mark_busy, mark_idle, mark_failed)
    - Pool statistics (idle/busy/failed counts)
    - Agent failure handling and recovery

    Example:
        >>> pool = AgentPool(org_id="123", token="abc", max_agents=5)
        >>> agent = pool.get_idle_agent()
        >>> if agent:
        ...     pool.mark_busy(agent, "task-1")
        ...     # ... execute task ...
        ...     pool.mark_idle(agent)

    Attributes:
        org_id: Codegen organization ID
        token: Codegen API token
        max_agents: Maximum number of agents in the pool (1-10)
        agents: List of managed agents
    """

    def __init__(self, org_id: str, token: str, max_agents: int = DEFAULT_MAX_AGENTS):
        """Initialize the agent pool.

        Args:
            org_id: Codegen organization ID
            token: Codegen API token
            max_agents: Maximum number of agents in pool (default: 10, max: 10)

        Raises:
            ValueError: If max_agents is not in valid range [1, 10]
        """
        if not MIN_AGENTS <= max_agents <= MAX_AGENTS_LIMIT:
            msg = f"max_agents must be between {MIN_AGENTS} and {MAX_AGENTS_LIMIT}, got {max_agents}"
            raise ValueError(msg)

        self.org_id = org_id
        self.token = token
        self.max_agents = max_agents
        self.agents: list[ManagedAgent] = []

        logger.info(
            "initializing_agent_pool",
            org_id=org_id,
            max_agents=max_agents,
        )

        self._initialize_pool()

        logger.info(
            "agent_pool_initialized",
            pool_size=len(self.agents),
        )

    def _initialize_pool(self) -> None:
        """Initialize the agent pool with Codegen agents.

        Creates max_agents number of Codegen Agent instances and wraps
        them in ManagedAgent objects with IDLE status.
        """
        for i in range(self.max_agents):
            try:
                agent = Agent(token=self.token, org_id=int(self.org_id))
                managed_agent = ManagedAgent(
                    id=i,
                    agent=agent,
                    status=AgentStatus.IDLE,
                )
                self.agents.append(managed_agent)
                logger.debug("agent_created", agent_id=i)
            except Exception as e:
                logger.exception(
                    "agent_creation_failed",
                    agent_id=i,
                    error=str(e),
                )
                raise

    def get_idle_agent(self) -> ManagedAgent | None:
        """Get an idle agent from the pool.

        Returns the first available agent with IDLE status.
        If no idle agents are available, returns None.

        Returns:
            ManagedAgent if an idle agent is available, None otherwise

        Example:
            >>> agent = pool.get_idle_agent()
            >>> if agent:
            ...     print(f"Got agent {agent.id}")
            ... else:
            ...     print("No idle agents available")
        """
        for agent in self.agents:
            if agent.status == AgentStatus.IDLE:
                logger.debug("idle_agent_found", agent_id=agent.id)
                return agent

        logger.debug("no_idle_agents_available")
        return None

    def mark_busy(self, agent: ManagedAgent, task_id: str) -> None:
        """Mark an agent as busy with a task.

        Transitions the agent's status to BUSY and assigns the task ID.

        Args:
            agent: The ManagedAgent to mark as busy
            task_id: ID of the task being assigned to the agent

        Raises:
            ValueError: If agent is not in IDLE status

        Example:
            >>> agent = pool.get_idle_agent()
            >>> pool.mark_busy(agent, "task-123")
        """
        if agent.status != AgentStatus.IDLE:
            msg = f"Cannot mark agent {agent.id} as busy: current status is {agent.status.value}"
            logger.error(
                "invalid_status_transition",
                agent_id=agent.id,
                current_status=agent.status.value,
                requested_status="busy",
                error=msg,
            )
            raise ValueError(msg)

        agent.status = AgentStatus.BUSY
        agent.current_task = task_id

        logger.info(
            "agent_marked_busy",
            agent_id=agent.id,
            task_id=task_id,
        )

    def mark_idle(self, agent: ManagedAgent) -> None:
        """Mark an agent as idle.

        Transitions the agent's status to IDLE and clears the task assignment.
        This should be called when an agent completes or cancels a task.

        Args:
            agent: The ManagedAgent to mark as idle

        Example:
            >>> pool.mark_idle(agent)
        """
        previous_status = agent.status
        previous_task = agent.current_task

        agent.status = AgentStatus.IDLE
        agent.current_task = None

        logger.info(
            "agent_marked_idle",
            agent_id=agent.id,
            previous_status=previous_status.value,
            previous_task=previous_task,
        )

    def mark_failed(self, agent: ManagedAgent, error: str | None = None) -> None:
        """Mark an agent as failed.

        Transitions the agent's status to FAILED and clears the task assignment.
        Failed agents are not automatically recovered and remain unavailable
        until manually reset or the pool is reinitialized.

        Args:
            agent: The ManagedAgent to mark as failed
            error: Optional error message describing the failure

        Example:
            >>> try:
            ...     # execute task
            ... except Exception as e:
            ...     pool.mark_failed(agent, str(e))
        """
        previous_status = agent.status
        previous_task = agent.current_task

        agent.status = AgentStatus.FAILED
        task_id = agent.current_task
        agent.current_task = None

        logger.error(
            "agent_marked_failed",
            agent_id=agent.id,
            previous_status=previous_status.value,
            previous_task=previous_task,
            task_id=task_id,
            error=error,
        )

    def get_stats(self) -> dict[str, int]:
        """Get pool statistics.

        Returns counts of agents in each status.

        Returns:
            Dictionary with keys 'idle', 'busy', 'failed' and their counts

        Example:
            >>> stats = pool.get_stats()
            >>> print(f"Idle: {stats['idle']}, Busy: {stats['busy']}")
        """
        stats = {
            "idle": sum(1 for agent in self.agents if agent.status == AgentStatus.IDLE),
            "busy": sum(1 for agent in self.agents if agent.status == AgentStatus.BUSY),
            "failed": sum(
                1 for agent in self.agents if agent.status == AgentStatus.FAILED
            ),
        }

        logger.debug("pool_stats_retrieved", **stats)
        return stats

    def get_total_agents(self) -> int:
        """Get total number of agents in the pool.

        Returns:
            Total agent count

        Example:
            >>> total = pool.get_total_agents()
        """
        return len(self.agents)

    def reset_agent(self, agent: ManagedAgent) -> None:
        """Reset a failed agent back to idle status.

        Allows recovery of failed agents by transitioning them back to IDLE.
        This can be used to implement manual or automatic agent recovery strategies.

        Args:
            agent: The ManagedAgent to reset

        Raises:
            ValueError: If agent is not in FAILED status

        Example:
            >>> if agent.status == AgentStatus.FAILED:
            ...     pool.reset_agent(agent)
        """
        if agent.status != AgentStatus.FAILED:
            msg = f"Cannot reset agent {agent.id}: current status is {agent.status.value}, expected FAILED"
            logger.error(
                "invalid_agent_reset",
                agent_id=agent.id,
                current_status=agent.status.value,
                error=msg,
            )
            raise ValueError(msg)

        agent.status = AgentStatus.IDLE
        agent.current_task = None

        logger.info("agent_reset", agent_id=agent.id)
