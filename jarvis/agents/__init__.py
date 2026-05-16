"""Jarvis specialist agents — sales, research, email, customer."""
from jarvis.agents.base import BaseAgent, AgentResponse
from jarvis.agents.sales_agent import SalesAgent
from jarvis.agents.research_agent import ResearchAgent
from jarvis.agents.email_agent import EmailAgent
from jarvis.agents.customer_agent import CustomerAgent
from jarvis.agents.router import detect_agent, route_to_agent

__all__ = [
    "BaseAgent",
    "AgentResponse",
    "SalesAgent",
    "ResearchAgent",
    "EmailAgent",
    "CustomerAgent",
    "detect_agent",
    "route_to_agent",
]
