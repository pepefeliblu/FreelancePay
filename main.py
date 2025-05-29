import argparse
from jira import JIRA
import os
from dotenv import load_dotenv
from git import Repo
from datetime import datetime
import re

# Load environment variables for Jira credentials
load_dotenv()
JIRA_URL = os.getenv("JIRA_URL")
JIRA_USERNAME = os.getenv("JIRA_USERNAME")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Initialize Jira client
jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USERNAME, JIRA_API_TOKEN))

def fetch_tasks(assignee, start_date, end_date):
    """Fetch tasks from Jira assigned to the user within the date range."""
    jql = f'assignee = "{assignee}" AND updated >= "{start_date}" AND updated <= "{end_date}"'
    issues = jira.search_issues(jql)
    return [(issue.key, issue.fields.summary) for issue in issues]

def fetch_commits(repo_path, author, start_date, end_date):
    """Fetch commits from Git made by the author within the date range."""
    repo = Repo(repo_path)
    commits = list(repo.iter_commits(since=start_date, until=end_date, author=author))
    return [(commit.hexsha, commit.message, commit.committed_datetime) for commit in commits]

def correlate_commits(commits, task_pattern=r'\b([A-Z]+-\d+)\b'):
    """Link commits to tasks based on task IDs in commit messages."""
    task_commits = {}
    for commit in commits:
        task_ids = re.findall(task_pattern, commit[1])
        for task_id in task_ids:
            if task_id not in task_commits:
                task_commits[task_id] = []
            task_commits[task_id].append(commit)
    return task_commits

def generate_report(tasks, task_commits, output_file):
    """Generate a text report listing tasks and their associated commits."""
    with open(output_file, 'w') as f:
        f.write("Work Report\n")
        f.write(f"Generated on: {datetime.now()}\n\n")
        for task_id, task_title in tasks:
            f.write(f"Task: {task_id} - {task_title}\n")
            if task_id in task_commits:
                for commit in task_commits[task_id]:
                    f.write(f"  - {commit[0][:8]}: {commit[1].strip()} ({commit[2]})\n")
            else:
                f.write("  No commits found for this task.\n")
            f.write("\n")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate work report for freelance developers.")
    parser.add_argument("--assignee", required=True, help="Jira assignee username")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--repo-path", required=True, help="Path to the Git repository")
    parser.add_argument("--output", required=True, help="Output report file")
    args = parser.parse_args()

    # Fetch data
    tasks = fetch_tasks(args.assignee, args.start_date, args.end_date)
    commits = fetch_commits(args.repo_path, args.assignee, args.start_date, args.end_date)

    # Correlate tasks and commits
    task_commits = correlate_commits(commits)

    # Generate the report
    generate_report(tasks, task_commits, args.output)
    print(f"Report generated successfully at {args.output}")

if __name__ == "__main__":
    main()