import json
from Models.log_agent import IssueReport, IssuesReported
from langchain_core.messages import AIMessage

def _parse_tool_logs(content) -> list[dict]:
    if isinstance(content, list):
        return [entry for entry in content if isinstance(entry, dict)]
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [entry for entry in parsed if isinstance(entry, dict)]
    return []


def _format_issue_item(issue_item: IssueReport) -> str:
    lines = [
        f"Category: {issue_item.category}",
        f"Priority: {issue_item.priority}",
        f"Issue: {issue_item.issue}",
    ]
    if issue_item.generic_recommendation:
        lines.append(f"Generic recommendation: {issue_item.generic_recommendation}")
    if issue_item.specific_recommendation:
        lines.append(f"Specific recommendation: {issue_item.specific_recommendation}")
    if issue_item.solution_steps:
        lines.append("Solution steps:")
        lines.extend(f"  - {step}" for step in issue_item.solution_steps)
    return "\n".join(lines)


def issues_to_message(reported: IssuesReported) -> AIMessage:
    if not reported.issues:
        return AIMessage(content="No issues were identified in the analyzed logs.")

    issue_blocks = [
        f"Issue {index}:\n{_format_issue_item(item)}"
        for index, item in enumerate(reported.issues, start=1)
    ]
    return AIMessage(
        content="\n\n".join(issue_blocks),
        additional_kwargs={"issues_report": reported.model_dump()},
    )