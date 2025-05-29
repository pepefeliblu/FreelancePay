# Work Report Generator

This tool is designed to help freelance developers automate the process of generating work reports for clients. It integrates with Jira and Git to cross-reference tasks with commits, providing a clear justification for hours worked.

## Problem Solved

Freelance developers often face the challenge of manually creating detailed reports to justify their hours to clients. This process can be time-consuming and error-prone. The Work Report Generator solves this problem by automatically fetching tasks from Jira and commits from Git, linking them based on task IDs in commit messages, and generating a simple text-based report.

## Key Features

- **Jira Integration**: Fetches tasks assigned to the user within a specified date range.
- **Git Integration**: Fetches commits authored by the user within the same date range.
- **Task-Commit Correlation**: Links commits to tasks using task IDs in commit messages.
- **Report Generation**: Creates a text-based report listing tasks and their associated commits.

## Technologies Used

- **Python**: The core programming language.
- **Jira API**: For interacting with Jira.
- **GitPython**: For accessing Git commit history.
- **python-dotenv**: For securely managing credentials.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install jira GitPython python-dotenv
   ```

2. **Create a `.env` File**:
   - Add your Jira credentials to a `.env` file in the project root:
     ```
     JIRA_URL=https://your-jira-instance.atlassian.net
     JIRA_USERNAME=your-email@example.com
     JIRA_API_TOKEN=your-api-token
     ```
   - Generate a Jira API token from your [Atlassian account settings](https://id.atlassian.com/manage-profile/security/api-tokens).

## Usage

1. **Run the Script**:
   ```bash
   python generate_work_report.py --assignee "your-username" --start-date "2023-10-01" --end-date "2023-10-31" --repo-path "/path/to/repo" --output "report.txt"
   ```

2. **Arguments**:
   - `--assignee`: Your Jira username.
   - `--start-date`: Start date for the report (YYYY-MM-DD).
   - `--end-date`: End date for the report (YYYY-MM-DD).
   - `--repo-path`: Path to the local Git repository.
   - `--output`: Output file for the generated report.

3. **Sample Output**:
   ```
   Work Report
   Generated on: 2023-11-01 10:00:00

   Task: TASK-123 - Fix login bug
     - a1b2c3d4: Fixed TASK-123 login issue (2023-10-05 14:32:00)
     - e5f6g7h8: Updated TASK-123 error handling (2023-10-06 09:15:00)

   Task: TASK-124 - Add new feature
     No commits found for this task.
   ```

## Key Considerations

- **Task ID Convention**: Ensure commit messages include task IDs (e.g., "TASK-123"). If not, the tool won't be able to link commits to tasks.
- **Time Zones**: The script assumes consistent time zones for Jira and Git data. Adjust if necessary.
- **Error Handling**: The MVP handles missing commits gracefully but could be expanded for more robustness.

## Future Enhancements

- Support for other project management tools (e.g., MS Project).
- NLP for summarizing commit messages (e.g., using `transformers`).
- Integration with time tracking tools for precise hours.
- Web interface for easier use and accessibility.