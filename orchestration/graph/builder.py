from orchestration.graph.state import AgentState
from langgraph.graph import StateGraph, END
from orchestration.graph.constants import SUPERVISOR, WORKER_NEWS, WORKER_TECH, WORKER_TRADE_BRAIN

from orchestration.graph.nodes.supervisor_nodes import supervisor_node
from orchestration.graph.nodes.worker_nodes import news_agent_node, technical_agent_node, trade_brain_agent_node

def build_graph():
    workflow = StateGraph(AgentState)

    # Add Nodes
    workflow.add_node(SUPERVISOR, supervisor_node)
    workflow.add_node(WORKER_NEWS, news_agent_node)
    workflow.add_node(WORKER_TECH, technical_agent_node)
    workflow.add_node(WORKER_TRADE_BRAIN, trade_brain_agent_node)

    # Hub and Spoke: All workers route back to Supervisor
    workflow.add_edge(WORKER_NEWS, SUPERVISOR)
    workflow.add_edge(WORKER_TECH, SUPERVISOR)
    workflow.add_edge(WORKER_TRADE_BRAIN, SUPERVISOR)

    # Supervisor routes dynamically
    workflow.add_conditional_edges(
        SUPERVISOR,
        lambda state: state.get("next", "FINISH"),
        {
            WORKER_NEWS: WORKER_NEWS,
            WORKER_TECH: WORKER_TECH,
            WORKER_TRADE_BRAIN: WORKER_TRADE_BRAIN,
            "FINISH": END
        }
    )
    
    workflow.set_entry_point(SUPERVISOR)
    
    from orchestration.config import HUMAN_IN_THE_LOOP
    if HUMAN_IN_THE_LOOP:
        graph = workflow.compile(interrupt_before=[WORKER_TRADE_BRAIN])
    else:
        graph = workflow.compile()
    
    return graph
