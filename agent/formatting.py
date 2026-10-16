import json

from langchain_core.messages import AIMessage

from agent.schemas import IssueCitation, IssueReport, IssuesReported


def message_text(content) -> str:
    """Normalize Bedrock/LangChain message content (str or content blocks) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return str(content)


def _format_citation(citation: IssueCitation) -> str | None:
    if citation.file_path and citation.line_number is not None:
        return f"{citation.file_path}:{citation.line_number}"
    if citation.file_path:
        return citation.file_path
    return None


def _format_issue_item(issue_item: IssueReport) -> str:
    lines = [
        f"Category: {issue_item.category}",
        f"Priority: {issue_item.priority}",
        f"Issue: {issue_item.issue}",
    ]
    if issue_item.generic_recommendation:
        lines.append(f"Generic recommendation: {issue_item.generic_recommendation}")
    if issue_item.timestamp:
        lines.append(f"Timestamp: {issue_item.timestamp}")
    if issue_item.machine:
        lines.append(f"Machine: {issue_item.machine}")
    rendered = [
        text
        for citation in (issue_item.citations or [])
        if (text := _format_citation(citation))
    ]
    if rendered:
        lines.append("Citations:")
        lines.extend(f"  - {item}" for item in rendered)
    return "\n".join(lines)


def issues_to_message(reported: IssuesReported, *, as_json: bool = False) -> AIMessage:
    payload = reported.model_dump()
    if as_json:
        return AIMessage(
            content=json.dumps(payload, indent=2),
            additional_kwargs={"issues_report": payload},
        )
    if not reported.issues:
        return AIMessage(content="No issues were identified in the analyzed logs.")

    issue_blocks = [
        f"Issue {index}:\n{_format_issue_item(item)}"
        for index, item in enumerate(reported.issues, start=1)
    ]
    return AIMessage(
        content="\n\n".join(issue_blocks),
        additional_kwargs={"issues_report": payload},
    )
