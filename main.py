import argparse
from jira import JIRA
import git
import openai
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Check for required environment variables
required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "OPENAI_API_KEY"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"Error: Missing environment variables: {', '.join(missing_vars)}")
    exit(1)

# Set OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

def fetch_tasks(jira, assignee, start_date, end_date):
    """Fetch tasks from Jira assigned to the user within the date range."""
    jql = f'assignee = "{assignee}" AND updated >= "{start_date}" AND updated <= "{end_date}"'
    issues = jira.search_issues(jql, fields=['summary', 'issuetype', 'priority'])
    tasks = []
    for issue in issues:
        task = {
            'id': issue.key,
            'title': issue.fields.summary,
            'type': issue.fields.issuetype.name,
            'priority': issue.fields.priority.name,
        }
        tasks.append(task)
    return tasks

def fetch_commits(repo, task_id, start_date, end_date):
    """Fetch commits from Git that mention the task ID and are within the date range."""
    commits = [c for c in repo.iter_commits(since=start_date, until=end_date) if task_id in c.message]
    return commits

def estimate_time(commits):
    """Estimate time spent based on commit history."""
    if not commits:
        return 0
    elif len(commits) == 1:
        return 0.5  # Default time for tasks with a single commit
    else:
        times = [c.authored_datetime for c in commits]
        first, last = min(times), max(times)
        hours = (last - first).total_seconds() / 3600
        return min(hours, 4)  # Cap at 4 hours

def generate_summary(tasks):
    """Generate a human-like summary using OpenAI's API."""
    prompt = "Generate a concise, professional summary of the following work:\n"
    for task in tasks:
        time_str = f"{task['time']:.1f} hours" if task['time'] > 0 else "no time estimated"
        prompt += f"- Task {task['id']}: {task['title']} ({task['type']}, {task['priority']} priority), estimated time: {time_str}\n"
    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            max_tokens=100
        )
        return response.choices[0].text.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return "Unable to generate summary."

def build_report(tasks, summary):
    """Build the report string."""
    report = f"Work Report\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += f"Summary: {summary}\n\n"
    report += "Details:\n"
    total_time = 0
    for task in tasks:
        report += f"Task: {task['id']} - {task['title']}\n"
        report += f"Type: {task['type']}\n"
        report += f"Priority: {task['priority']}\n"
        time_str = f"{task['time']:.1f} hours" if task['time'] > 0 else "no time estimated"
        report += f"Estimated Time: {time_str}\n"
        report += "Commits:\n"
        if task['commits']:
            for commit in task['commits']:
                commit_time = commit.authored_datetime.strftime("%Y-%m-%d %H:%M")
                report += f"  - {commit.hexsha[:8]}: {commit.message.strip()} ({commit_time})\n"
        else:
            report += "  No commits found for this task.\n"
        report += "\n"
        if task['time'] > 0:
            total_time += task['time']
    report += f"Total Estimated Time: {total_time:.1f} hours\n"
    return report

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate a work report with AI summary.")
    parser.add_argument("--assignee", required=True, help="Jira assignee username")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--repo-path", required=True, help="Path to the Git repository")
    parser.add_argument("--output", help="Output file path for the report (optional)")
    args = parser.parse_args()

    # Initialize Jira client with credentials from .env
    jira = JIRA(server=os.getenv("JIRA_URL"), basic_auth=(os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")))

    # Set up Git repository
    repo = git.Repo(args.repo_path)

    # Fetch tasks from Jira
    tasks = fetch_tasks(jira, args.assignee, args.start_date, args.end_date)

    # Process each task: fetch commits and estimate time
    for task in tasks:
        commits = fetch_commits(repo, task['id'], args.start_date, args.end_date)
        task['commits'] = commits
        task['time'] = estimate_time(commits)

    # Generate AI summary
    summary = generate_summary(tasks)

    # Build the report
    report = build_report(tasks, summary)

    # Output the report
    if args.output:
        try:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"Report saved to {args.output}")
        except IOError as e:
            print(f"Error writing to file: {e}")
    else:
        print(report)

if __name__ == "__main__":
    main()