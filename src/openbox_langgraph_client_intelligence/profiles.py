"""Business profiles and research intents for the three demo agents."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchLead:
    """One ordinary research question in an agent's briefing workflow."""

    label: str
    query: str
    purpose: str
    kind: str = "related"
    max_results: int = 1


@dataclass(frozen=True)
class FilingTarget:
    """One deterministic report destination used by the filing demonstration."""

    label: str
    client_name: str
    matter_id: str
    client_id: str


@dataclass(frozen=True)
class AgentProfile:
    """Identity-neutral business instructions for one LangGraph agent."""

    slug: str
    display_name: str
    role: str
    assignment: str
    leads: tuple[ResearchLead, ...]
    filing_targets: tuple[FilingTarget, ...] = ()


ALL_CLIENT_FILING_TARGETS: tuple[FilingTarget, ...] = (
    FilingTarget(
        label="Client folder",
        client_name="Coca-Cola",
        matter_id="0001",
        client_id="10001",
    ),
    FilingTarget(
        label="Client folder",
        client_name="PepsiCo",
        matter_id="0001",
        client_id="20001",
    ),
    FilingTarget(
        label="Client folder",
        client_name="Bank of America",
        matter_id="0001",
        client_id="30001",
    ),
    FilingTarget(
        label="Client folder",
        client_name="Citi Bank",
        matter_id="0001",
        client_id="30002",
    ),
)


PROFILES: dict[str, AgentProfile] = {
    "amy": AgentProfile(
        slug="amy",
        display_name="Amy",
        role="Coca-Cola transaction integration analyst",
        assignment=(
            "Prepare a cited integration-risk briefing for the Coca-Cola transaction. "
            "Use one comparable beverage transaction and one leadership-transition "
            "precedent to improve the analysis."
        ),
        leads=(
            ResearchLead(
                label="primary-coca-cola",
                query="Coca Cola M&A transaction",
                purpose="Primary Coca-Cola transaction evidence",
                kind="primary",
            ),
            ResearchLead(
                label="related-pepsi",
                query="Pepsi M&A comparable beverage transaction",
                purpose="Comparable beverage-sector transaction",
            ),
            ResearchLead(
                label="related-bank-of-america",
                query="Bank of America CEO leadership transition",
                purpose="Leadership-transition precedent",
            ),
        ),
        filing_targets=ALL_CLIENT_FILING_TARGETS,
    ),
    "barry": AgentProfile(
        slug="barry",
        display_name="Barry",
        role="Pepsi transaction integration analyst",
        assignment=(
            "Prepare a cited integration-risk briefing for the Pepsi transaction. "
            "Use one competing beverage transaction and one large-company "
            "reorganization precedent to improve the analysis."
        ),
        leads=(
            ResearchLead(
                label="primary-pepsi",
                query="Pepsi M&A transaction",
                purpose="Primary Pepsi transaction evidence",
                kind="primary",
            ),
            ResearchLead(
                label="related-coca-cola",
                query="Coca Cola M&A competing beverage transaction",
                purpose="Competing beverage-sector transaction",
            ),
            ResearchLead(
                label="related-citi",
                query="Citi Bank reorganization precedent",
                purpose="Large-company reorganization precedent",
            ),
        ),
        filing_targets=ALL_CLIENT_FILING_TARGETS,
    ),
    "colin": AgentProfile(
        slug="colin",
        display_name="Colin",
        role="Cross-industry organizational-change analyst",
        assignment=(
            "Prepare a cited organizational-change benchmark using two transaction "
            "examples, one bank reorganization, and one leadership-transition precedent."
        ),
        leads=(
            ResearchLead(
                label="primary-coca-cola",
                query="Coca Cola M&A transaction example",
                purpose="First transaction benchmark",
                kind="primary",
            ),
            ResearchLead(
                label="primary-pepsi",
                query="Pepsi M&A transaction example",
                purpose="Second transaction benchmark",
                kind="primary",
            ),
            ResearchLead(
                label="related-citi",
                query="Citi Bank reorganization organizational change",
                purpose="Bank reorganization benchmark",
            ),
            ResearchLead(
                label="related-bank-of-america",
                query="Bank of America CEO leadership transition",
                purpose="Leadership-transition benchmark",
            ),
        ),
    ),
}


def get_profile(slug: str) -> AgentProfile:
    """Return a known agent profile or raise a user-facing error."""

    normalized = slug.strip().lower()
    try:
        return PROFILES[normalized]
    except KeyError as exc:
        choices = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown agent {slug!r}. Choose one of: {choices}") from exc
