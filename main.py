import os
import argparse
from jira import JIRA
import git
from datetime import datetime
from dotenv import load_dotenv

# Constants
NO_TASKS_COMPLETED_MESSAGE = "No tasks completed during this period."

# Load environment variables from .env file
load_dotenv()

# Check for required environment variables
required_vars = ["JIRA_URL", "JIRA_USERNAME", "JIRA_API_TOKEN"]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    print(f"Error: Missing environment variables: {', '.join(missing_vars)}")
    exit(1)

# Initialize AI clients (optional - will fallback if not available)
openai_client = None
gemini_model = None

# Try to initialize OpenAI
if os.getenv("OPENAI_API_KEY"):
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        print("✅ OpenAI client initialized")
    except ImportError:
        print("⚠️ OpenAI package not installed")

# Try to initialize Gemini
if os.getenv("GEMINI_API_KEY"):
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        # Try the newer model names first
        try:
            gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            print("✅ Gemini client initialized (using gemini-1.5-flash)")
        except Exception:
            try:
                gemini_model = genai.GenerativeModel('gemini-1.5-pro')
                print("✅ Gemini client initialized (using gemini-1.5-pro)")
            except Exception:
                # Fallback to listing available models
                try:
                    models = list(genai.list_models())
                    available_models = [model.name for model in models if 'generateContent' in model.supported_generation_methods]
                    if available_models:
                        # Use the first available model
                        model_name = available_models[0].replace('models/', '')
                        gemini_model = genai.GenerativeModel(model_name)
                        print(f"✅ Gemini client initialized (using {model_name})")
                    else:
                        print("⚠️ No compatible Gemini models found")
                        gemini_model = None
                except Exception as e:
                    print(f"⚠️ Could not initialize Gemini: {e}")
                    gemini_model = None
    except ImportError:
        print("⚠️ Google AI package not installed")

def parse_assignee_info(current_assignee, target_assignee):
    """Parse and validate assignee information."""
    if not current_assignee:
        return False
    
    assignee_email = getattr(current_assignee, 'emailAddress', '')
    assignee_name = getattr(current_assignee, 'name', '')
    assignee_display = getattr(current_assignee, 'displayName', '')
    
    return target_assignee in [assignee_email, assignee_name, assignee_display]

def extract_time_fields(issue):
    """Extract time tracking information from JIRA issue."""
    time_spent_seconds = getattr(issue.fields, 'timespent', None) or 0
    time_estimate_seconds = getattr(issue.fields, 'timeoriginalestimate', None) or 0
    aggregate_time_seconds = getattr(issue.fields, 'aggregatetimespent', None) or 0
    
    return {
        'jira_time_spent': time_spent_seconds / 3600 if time_spent_seconds else 0,
        'jira_time_estimate': time_estimate_seconds / 3600 if time_estimate_seconds else 0,
        'jira_aggregate_time': aggregate_time_seconds / 3600 if aggregate_time_seconds else 0
    }

def detect_sprint_info(issue):
    """Detect sprint information from various JIRA field formats."""
    sprint_field_candidates = ['sprint', 'customfield_10020', 'customfield_10010', 'customfield_10001']
    
    for field_name in sprint_field_candidates:
        sprint_info, sprint_status = try_extract_sprint_from_field(issue, field_name)
        if sprint_info:
            return sprint_info, sprint_status
    
    return None, "Unknown"

def try_extract_sprint_from_field(issue, field_name):
    """Try to extract sprint information from a specific field."""
    try:
        sprint_field = getattr(issue.fields, field_name, None)
        if not sprint_field:
            return None, "Unknown"
        
        if isinstance(sprint_field, list) and sprint_field:
            return parse_sprint_object(sprint_field[-1])
        elif isinstance(sprint_field, str) and sprint_field:
            return sprint_field, "Active"
        elif hasattr(sprint_field, 'name'):
            return parse_sprint_object(sprint_field)
    except (AttributeError, TypeError):
        pass
    
    return None, "Unknown"

def parse_sprint_object(sprint_obj):
    """Parse a sprint object to extract name and status."""
    sprint_info = str(sprint_obj)
    
    if hasattr(sprint_obj, 'name'):
        sprint_info = getattr(sprint_obj, 'name', 'Unknown')
    
    if hasattr(sprint_obj, 'state'):
        state = getattr(sprint_obj, 'state', 'UNKNOWN')
        sprint_status = map_sprint_state(state)
    else:
        sprint_status = parse_sprint_state_from_string(sprint_info)
    
    return sprint_info, sprint_status

def map_sprint_state(state):
    """Map JIRA sprint state to our status categories."""
    if state in ['CLOSED', 'COMPLETE']:
        return "Closed"
    elif state in ['ACTIVE', 'OPEN']:
        return "Active"
    else:
        return "Future"

def parse_sprint_state_from_string(sprint_info):
    """Parse sprint status from string representation."""
    if 'state=CLOSED' in sprint_info or 'state=COMPLETE' in sprint_info:
        return "Closed"
    elif 'state=ACTIVE' in sprint_info or 'state=OPEN' in sprint_info:
        return "Active"
    else:
        return "Future"

def is_task_in_date_range(issue, start_date, end_date):
    """Check if task falls within the specified date range."""
    created_date = getattr(issue.fields, 'created', None)
    updated_date = getattr(issue.fields, 'updated', None)
    resolved_date = getattr(issue.fields, 'resolved', None)
    
    for date_field in [created_date, updated_date, resolved_date]:
        if date_field and check_date_in_range(date_field, start_date, end_date):
            return True
    
    # If we can't determine dates, include the task
    if not any([created_date, updated_date, resolved_date]):
        return True
    
    return False

def check_date_in_range(date_field, start_date, end_date):
    """Check if a specific date falls within the range."""
    try:
        if isinstance(date_field, str):
            date_obj = datetime.fromisoformat(date_field.replace('Z', '+00:00'))
        else:
            date_obj = date_field
        
        task_date = date_obj.date()
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        return start_dt <= task_date <= end_dt
    except (ValueError, AttributeError):
        return False

def fetch_tasks(jira, assignee, start_date, end_date):
    """Fetch tasks from Jira assigned to the user within the date range, focusing on actual work done."""
    
    print(f"🔍 Fetching tasks for {assignee}...")
    
    # Start with a simpler, more compatible query
    basic_jql = f'assignee = "{assignee}" AND updated >= "{start_date}" AND updated <= "{end_date}"'
    
    # Include time tracking fields and sprint information
    fields = [
        'summary', 'issuetype', 'priority', 'status', 'assignee',
        'timeoriginalestimate', 'timespent', 'aggregatetimespent', 'timeestimate',
        'created', 'updated', 'resolved', 'resolutiondate',
        'customfield_10020', 'sprint', 'fixVersions', 'labels'
    ]
    
    try:
        issues = jira.search_issues(basic_jql, fields=fields, maxResults=100)
        print(f"✅ Found {len(issues)} tasks using basic query")
    except Exception as e:
        print(f"⚠️ Query failed: {e}")
        # Even more basic fallback
        minimal_jql = f'assignee = "{assignee}"'
        issues = jira.search_issues(minimal_jql, fields=['summary', 'issuetype', 'priority'], maxResults=50)
        print(f"✅ Found {len(issues)} tasks using minimal query")
    
    tasks = []
    for issue in issues:
        # Verify assignee
        if not parse_assignee_info(getattr(issue.fields, 'assignee', None), assignee):
            continue
        
        # Extract time information
        time_info = extract_time_fields(issue)
        
        # Detect sprint information
        sprint_info, sprint_status = detect_sprint_info(issue)
        
        # Get task status and dates
        task_status = getattr(issue.fields, 'status', None)
        task_status_name = getattr(task_status, 'name', 'Unknown') if task_status else 'Unknown'
        
        created_date = getattr(issue.fields, 'created', None)
        updated_date = getattr(issue.fields, 'updated', None)
        resolved_date = getattr(issue.fields, 'resolved', None)
        
        # Filter by date range
        if not is_task_in_date_range(issue, start_date, end_date):
            continue
        
        task = {
            'id': issue.key,
            'title': issue.fields.summary,
            'type': issue.fields.issuetype.name,
            'priority': issue.fields.priority.name if issue.fields.priority else 'Medium',
            'status': task_status_name,
            'sprint_info': sprint_info,
            'sprint_status': sprint_status,
            'created_date': created_date,
            'updated_date': updated_date,
            'resolved_date': resolved_date,
            'assignee_email': assignee,
            **time_info
        }
        tasks.append(task)
    
    print(f"📊 Found {len(tasks)} relevant tasks for {assignee}")
    
    # Group by sprint status for reporting
    sprint_summary = {}
    for task in tasks:
        status = task['sprint_status']
        sprint_summary[status] = sprint_summary.get(status, 0) + 1
    
    print(f"📈 Sprint distribution: {sprint_summary}")
    
    return tasks

def fetch_commits_from_multiple_repos(repo_paths, task_id, start_date, end_date):
    """Fetch commits from multiple Git repositories that mention the task ID and are within the date range."""
    all_commits = []
    repo_sources = {}
    
    for repo_path in repo_paths:
        try:
            repo = git.Repo(repo_path)
            repo_name = repo_path.split('/')[-1]  # Get repository name from path
            commits = [c for c in repo.iter_commits(since=start_date, until=end_date) if task_id in c.message]
            
            if commits:
                print(f"  📁 {repo_name}: {len(commits)} commits")
                all_commits.extend(commits)
                repo_sources[repo_name] = len(commits)
            
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError) as e:
            print(f"  ⚠️ Skipping invalid repo {repo_path}: {e}")
        except Exception as e:
            print(f"  ⚠️ Error accessing repo {repo_path}: {e}")
    
    if repo_sources:
        sources_str = ", ".join([f"{name}({count})" for name, count in repo_sources.items()])
        print(f"  🔍 Total: {len(all_commits)} commits from {sources_str}")
    
    return all_commits, repo_sources

def fetch_commits(repo, task_id, start_date, end_date):
    """Fetch commits from Git that mention the task ID and are within the date range (single repo)."""
    commits = [c for c in repo.iter_commits(since=start_date, until=end_date) if task_id in c.message]
    return commits

def estimate_realistic_time(commits, task_title, task_type, task_priority):
    """
    Estimate realistic time spent including all development activities.
    Git commits only show code delivery time, not research, planning, testing, debugging, etc.
    """
    if not commits:
        # Tasks without commits might still represent planning, research, or coordination work
        base_time = get_base_task_time(task_title, task_type)
        return base_time * 0.3  # Some work done but not committed
    
    # Start with git-based time estimation (for commit activity)
    git_time = estimate_git_commit_time(commits)
    
    # Apply realistic multipliers based on development reality
    complexity_multiplier = get_complexity_multiplier(task_title, task_type)
    priority_multiplier = get_priority_multiplier(task_priority)
    
    # Base realistic time includes:
    # - Planning and research (30-50% of commit time)
    # - Testing and debugging (50-100% of commit time)  
    # - Code review and iteration (20-40% of commit time)
    # - Integration and deployment (10-30% of commit time)
    
    realistic_multiplier = 2.5 + (complexity_multiplier - 1.0) + (priority_multiplier - 1.0)
    realistic_time = git_time * realistic_multiplier
    
    # Minimum time based on task type
    min_time = get_minimum_task_time(task_type)
    
    return max(realistic_time, min_time)

def estimate_git_commit_time(commits):
    """Original git-based time estimation for commit activity only."""
    if len(commits) == 1:
        return 1.0  # Single commit represents focused work
    else:
        times = [c.authored_datetime for c in commits]
        first, last = min(times), max(times)
        hours = (last - first).total_seconds() / 3600
        
        if hours < 0.5:
            return max(len(commits) * 0.5, 1.0)
        elif hours < 2:
            return max(hours * 1.2, 1.5)
        elif hours > 24:
            days = hours / 24
            commits_per_day = len(commits) / days
            return min(commits_per_day * 2.0, 8.0)
        else:
            return min(max(hours * 1.3, 2.0), 8.0)

def get_complexity_multiplier(task_title, task_type):
    """Determine complexity multiplier based on task characteristics."""
    title_lower = task_title.lower()
    type_lower = task_type.lower()
    
    # High complexity indicators
    high_complexity_keywords = [
        'integration', 'migration', 'refactor', 'architecture', 'security', 
        'performance', 'optimization', 'algorithm', 'complex', 'system'
    ]
    
    # Medium complexity indicators  
    medium_complexity_keywords = [
        'feature', 'implementation', 'enhancement', 'workflow', 'process',
        'validation', 'authentication', 'database', 'api'
    ]
    
    # Simple task indicators
    simple_keywords = [
        'fix', 'update', 'minor', 'text', 'styling', 'copy', 'simple'
    ]
    
    if any(keyword in title_lower for keyword in high_complexity_keywords):
        return 1.8  # 80% more time for complex tasks
    elif any(keyword in title_lower for keyword in medium_complexity_keywords):
        return 1.4  # 40% more time for medium tasks
    elif any(keyword in title_lower for keyword in simple_keywords):
        return 1.0  # Standard time for simple tasks
    elif 'story' in type_lower or 'epic' in type_lower:
        return 1.6  # Stories typically involve multiple aspects
    else:
        return 1.2  # Default slight increase

def get_priority_multiplier(task_priority):
    """Adjust time based on priority (high priority often means more pressure/coordination)."""
    priority_lower = task_priority.lower()
    
    if priority_lower in ['highest', 'critical']:
        return 1.3  # More coordination and testing for critical items
    elif priority_lower in ['high']:
        return 1.1  # Some additional overhead
    else:
        return 1.0  # Standard time

def get_minimum_task_time(task_type):
    """Minimum realistic time for any development task."""
    type_lower = task_type.lower()
    
    # Minimum times based on task type (realistic development time)
    if 'epic' in type_lower:
        return 8.0  # Epics are substantial
    elif 'story' in type_lower:
        return 4.0  # User stories involve analysis, development, testing
    elif 'task' in type_lower:
        return 2.0  # Even simple tasks need analysis and testing
    elif 'bug' in type_lower:
        return 3.0  # Bugs need investigation, fix, testing, verification
    else:
        return 2.0  # Default minimum

def get_base_task_time(task_title, task_type):
    """Estimate base time for tasks without commits (planning, analysis, etc.)."""
    type_lower = task_type.lower()
    title_lower = task_title.lower()
    
    # Research and planning tasks
    if any(keyword in title_lower for keyword in ['research', 'analysis', 'planning', 'design', 'spec']):
        return 4.0
    elif 'epic' in type_lower:
        return 6.0  # Epic planning
    elif 'story' in type_lower:
        return 3.0  # Story analysis
    else:
        return 1.5  # Basic task planning

def get_final_time_estimate(task, commits):
    """
    Get the final time estimate prioritizing JIRA logged time over git-based estimation.
    Priority: 1) JIRA logged time, 2) JIRA original estimate, 3) Git-based realistic estimate
    """
    
    # Priority 1: Use actual logged time in JIRA (most accurate)
    if task.get('jira_time_spent', 0) > 0:
        return task['jira_time_spent']
    
    # Priority 2: Use aggregate time spent (includes subtasks)
    if task.get('jira_aggregate_time', 0) > 0:
        return task['jira_aggregate_time']
    
    # Priority 3: Use original estimate if it seems reasonable and no time logged
    jira_estimate = task.get('jira_time_estimate', 0)
    if jira_estimate > 0:
        # If there are commits, the work was likely done, so use the estimate
        if commits:
            return jira_estimate
        # If no commits, they might have planned but not executed, so use partial estimate
        else:
            return jira_estimate * 0.2  # 20% for planning/analysis
    
    # Priority 4: Fall back to git-based realistic estimation
    return estimate_realistic_time(commits, task['title'], task['type'], task['priority'])

def analyze_time_source(tasks):
    """Analyze what time sources were used for reporting transparency."""
    jira_logged = 0
    jira_estimated = 0 
    git_estimated = 0
    
    for task in tasks:
        if task.get('jira_time_spent', 0) > 0 or task.get('jira_aggregate_time', 0) > 0:
            jira_logged += 1
        elif task.get('jira_time_estimate', 0) > 0:
            jira_estimated += 1
        else:
            git_estimated += 1
    
    return {
        'jira_logged': jira_logged,
        'jira_estimated': jira_estimated,
        'git_estimated': git_estimated,
        'total': len(tasks)
    }

def generate_summary(tasks):
    """Generate a human-like summary using available AI APIs or fallback to template."""
    
    # Analyze the actual work for specific insights
    completed_tasks = [task for task in tasks if task.get('commits')]
    total_time = sum(task['time'] for task in tasks if task['time'] > 0)
    
    # Extract specific work details for AI analysis
    work_details = []
    for task in completed_tasks[:10]:  # Focus on top completed tasks
        commits_summary = []
        if task.get('commits'):
            for commit in task['commits'][:3]:  # Top 3 commits per task
                commits_summary.append(commit.message.strip())
        
        work_details.append({
            'title': task['title'],
            'type': task['type'],
            'time': task['time'],
            'commits': commits_summary
        })
    
    # Create a rich prompt for AI analysis
    prompt = f"""Analyze this development work and provide specific business insights:

CONTEXT: {len(completed_tasks)} completed tasks, {total_time:.1f} hours of development work

COMPLETED WORK ANALYSIS:
"""
    
    for work in work_details:
        prompt += f"\nTask: {work['title']} ({work['type']}, {work['time']:.1f}h)\n"
        if work['commits']:
            prompt += f"Implementation: {'; '.join(work['commits'][:2])}\n"
    
    prompt += """
ANALYSIS REQUEST:
1. What specific business capabilities were delivered?
2. What user problems were solved?
3. What development patterns or trends are emerging?
4. What strategic recommendations would you make based on this work?
5. What potential risks or bottlenecks do you see?

Provide a concise but specific summary that a stakeholder would find valuable for decision-making."""
    
    # Try Gemini first (free tier is generous)
    if gemini_model:
        try:
            response = gemini_model.generate_content(
                f"You are a senior technical project manager analyzing development work for business stakeholders. {prompt}"
            )
            print("📝 AI-enhanced summary generated using Gemini")
            return response.text.strip()
        except Exception as e:
            print(f"Gemini API error: {e}")
    
    # Try OpenAI as fallback
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a senior technical project manager who creates insightful development summaries for business stakeholders. Focus on specific achievements, business impact, and strategic insights."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            print("📝 AI-enhanced summary generated using OpenAI")
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
    
    # Enhanced fallback with specific analysis
    print("📝 Using enhanced template-based summary")
    return generate_enhanced_template_summary(tasks, completed_tasks, total_time)

def generate_enhanced_template_summary(tasks, completed_tasks, total_time):
    """Generate an enhanced summary without AI that provides specific insights."""
    if not completed_tasks:
        return "No tasks completed during this period."
    
    # Analyze completed work for patterns
    feature_keywords = ['feature', 'add', 'new', 'implement', 'create']
    improvement_keywords = ['fix', 'improve', 'update', 'enhance', 'optimize']
    security_keywords = ['security', 'auth', 'token', 'validation', 'access']
    
    feature_work = []
    improvements = []
    security_work = []
    
    for task in completed_tasks:
        title_lower = task['title'].lower()
        if any(keyword in title_lower for keyword in feature_keywords):
            feature_work.append(task)
        elif any(keyword in title_lower for keyword in improvement_keywords):
            improvements.append(task)
        elif any(keyword in title_lower for keyword in security_keywords):
            security_work.append(task)
    
    # Build specific summary
    summary_parts = []
    
    # Overview
    working_days = 22
    daily_avg = total_time / working_days
    summary_parts.append(f"Delivered {len(completed_tasks)} development initiatives with {total_time:.1f} hours of professional development work ({daily_avg:.1f}h/day average).")
    
    # Specific achievements
    if feature_work:
        feature_time = sum(t['time'] for t in feature_work)
        summary_parts.append(f"New capabilities: {len(feature_work)} features developed ({feature_time:.1f}h investment), expanding platform functionality.")
    
    if improvements:
        improvement_time = sum(t['time'] for t in improvements)
        summary_parts.append(f"Platform enhancement: {len(improvements)} improvements implemented ({improvement_time:.1f}h investment), strengthening system reliability.")
    
    if security_work:
        security_time = sum(t['time'] for t in security_work)
        summary_parts.append(f"Security advancement: {len(security_work)} security enhancements ({security_time:.1f}h investment), improving system protection.")
    
    # Development velocity insight
    if len(completed_tasks) >= 3:
        avg_task_time = total_time / len(completed_tasks)
        if avg_task_time > 8:
            summary_parts.append(f"Development pattern: Complex feature work averaging {avg_task_time:.1f}h per task, indicating substantial technical implementations.")
        elif avg_task_time < 3:
            summary_parts.append(f"Development pattern: Efficient task completion averaging {avg_task_time:.1f}h per task, showing optimized development velocity.")
        else:
            summary_parts.append(f"Development pattern: Balanced development approach averaging {avg_task_time:.1f}h per task, maintaining steady delivery pace.")
    
    return " ".join(summary_parts)

def generate_template_summary(tasks):
    """Generate a summary without AI using templates."""
    total_tasks = len(tasks)
    total_time = sum(task['time'] for task in tasks if task['time'] > 0)
    
    if total_tasks == 0:
        return NO_TASKS_COMPLETED_MESSAGE
    
    # Categorize tasks
    bug_fixes, features, other = categorize_tasks_for_summary(tasks)
    
    # Build summary
    summary = build_task_summary_text(total_tasks, total_time)
    summary += build_task_details_text(bug_fixes, features, other)
    
    return summary

def categorize_tasks_for_summary(tasks):
    """Categorize tasks for summary generation."""
    bug_fixes = sum(1 for task in tasks if 'bug' in task['type'].lower() or 'defect' in task['type'].lower())
    features = sum(1 for task in tasks if 'story' in task['type'].lower() or 'feature' in task['type'].lower())
    other = len(tasks) - bug_fixes - features
    return bug_fixes, features, other

def build_task_summary_text(total_tasks, total_time):
    """Build the main summary text."""
    summary = f"Completed {total_tasks} task{'s' if total_tasks != 1 else ''}"
    if total_time > 0:
        summary += f" with an estimated {total_time:.1f} hours of work"
    summary += "."
    return summary

def build_task_details_text(bug_fixes, features, other):
    """Build the task details text."""
    details = []
    if features > 0:
        details.append(f"{features} feature{'s' if features != 1 else ''}/user stor{'ies' if features != 1 else 'y'}")
    if bug_fixes > 0:
        details.append(f"{bug_fixes} bug fix{'es' if bug_fixes != 1 else ''}")
    if other > 0:
        details.append(f"{other} other task{'s' if other != 1 else ''}")
    
    if details:
        return f" This included {', '.join(details)}."
    return ""

def format_task_header(task):
    """Format the header information for a task."""
    header = f"Task: {task['id']} - {task['title']}\n"
    header += f"Type: {task['type']}\n"
    header += f"Priority: {task['priority']}\n"
    
    time_str = f"{task['time']:.1f} hours" if task['time'] > 0 else "no time estimated"
    header += f"Estimated Time: {time_str}\n"
    
    return header

def format_repository_sources(task):
    """Format repository source information for a task."""
    if not task.get('repo_sources'):
        return ""
    
    repo_info = []
    for repo_name, commit_count in task['repo_sources'].items():
        if commit_count > 0:
            repo_info.append(f"{repo_name}({commit_count})")
    
    if repo_info:
        return f"Repository Sources: {', '.join(repo_info)}\n"
    
    return ""

def format_commits(task):
    """Format commit information for a task."""
    commits_section = "Commits:\n"
    
    if task['commits']:
        for commit in task['commits']:
            commit_time = commit.authored_datetime.strftime("%Y-%m-%d %H:%M")
            commits_section += f"  - {commit.hexsha[:8]}: {commit.message.strip()} ({commit_time})\n"
    else:
        commits_section += "  No commits found for this task.\n"
    
    return commits_section

def build_report(tasks, summary):
    """Build the technical report string."""
    report = f"Work Report\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += f"Summary: {summary}\n\n"
    report += "Details:\n"
    
    total_time = 0
    for task in tasks:
        report += format_task_header(task)
        report += format_repository_sources(task)
        report += format_commits(task)
        report += "\n"
        
        if task['time'] > 0:
            total_time += task['time']
    
    report += f"Total Estimated Time: {total_time:.1f} hours\n"
    return report

def get_business_categories():
    """Get the business impact categories configuration."""
    return {
        'revenue_generation': {
            'keywords': ['discount', 'coupon', 'cart', 'purchase', 'payment', 'checkout', 'billing'],
            'impact': 'Revenue & Sales',
            'tasks': []
        },
        'user_experience': {
            'keywords': ['login', 'session', 'redirection', 'thumbnail', 'theme', 'template', 'ui', 'ux'],
            'impact': 'User Experience',
            'tasks': []
        },
        'security_compliance': {
            'keywords': ['security', 'token', 'csrf', 'cookie', 'access', 'auth', 'validation'],
            'impact': 'Security & Compliance',
            'tasks': []
        },
        'operational_efficiency': {
            'keywords': ['admin', 'crud', 'filter', 'management', 'cron', 'automation'],
            'impact': 'Operational Efficiency',
            'tasks': []
        },
        'platform_stability': {
            'keywords': ['bug', 'fix', 'error', 'issue', 'storage', 'performance'],
            'impact': 'Platform Stability',
            'tasks': []
        },
        'feature_expansion': {
            'keywords': ['new', 'add', 'implement', 'create', 'feature', 'story'],
            'impact': 'Feature Expansion',
            'tasks': []
        }
    }

def categorize_tasks_by_business_value(tasks, categories):
    """Categorize tasks by business value."""
    uncategorized = []
    for task in tasks:
        categorized = False
        task_text = f"{task['title']} {task['type']}".lower()
        
        for category_key, category in categories.items():
            if any(keyword in task_text for keyword in category['keywords']):
                categories[category_key]['tasks'].append(task)
                categorized = True
                break
        
        if not categorized:
            uncategorized.append(task)
    
    return uncategorized

def calculate_business_metrics(tasks):
    """Calculate business metrics from tasks."""
    total_completed = len([t for t in tasks if t.get('commits')])
    total_time = sum(task['time'] for task in tasks if task['time'] > 0)
    high_priority = len([t for t in tasks if t['priority'].lower() in ['high', 'highest']])
    
    return {
        'total_tasks': len(tasks),
        'completed_tasks': total_completed,
        'total_time': total_time,
        'high_priority_tasks': high_priority,
        'completion_rate': (total_completed / len(tasks) * 100) if tasks else 0
    }

def analyze_business_impact(tasks):
    """Analyze business impact and categorize work by business value."""
    
    # Get business impact categories
    categories = get_business_categories()
    
    # Categorize tasks
    uncategorized = categorize_tasks_by_business_value(tasks, categories)
    
    # Calculate metrics
    metrics = calculate_business_metrics(tasks)
    
    return {
        'categories': categories,
        'uncategorized': uncategorized,
        'metrics': metrics
    }

def generate_strategic_development_metrics(metrics, completed_tasks):
    """Generate strategic development metrics."""
    if not completed_tasks:
        return ""
    
    avg_task_complexity = metrics['total_time'] / len(completed_tasks)
    return f"• **Strategic Development**: {len(completed_tasks)} complex initiatives averaging {avg_task_complexity:.1f}h each\n"

def generate_velocity_metrics(metrics):
    """Generate development velocity metrics."""
    working_days = 22
    daily_velocity = metrics['total_time'] / working_days
    return f"• **Development Velocity**: {daily_velocity:.1f} hours/day sustained pace over {working_days} working days\n"

def generate_repository_metrics(repo_distribution):
    """Generate multi-repository metrics."""
    if not repo_distribution or len(repo_distribution) <= 1:
        return ""
    
    sorted_repos = sorted(repo_distribution.items(), key=lambda x: x[1]['commits'], reverse=True)
    primary_repo = sorted_repos[0]
    
    return (f"• **Technical Scope**: Full-stack development across {len(repo_distribution)} repositories\n"
            f"• **Primary Focus**: {primary_repo[1]['commits']} commits in {primary_repo[0]} ({primary_repo[1]['time']:.1f}h)\n")

def generate_pipeline_health_metrics(tasks):
    """Generate pipeline health metrics."""
    active_tasks = len([t for t in tasks if t.get('commits') or t['time'] > 2.0])
    planning_tasks = len(tasks) - active_tasks
    
    if planning_tasks > 0:
        return f"• **Pipeline Health**: {active_tasks} active development items, {planning_tasks} strategic planning items\n"
    
    return ""

def generate_quality_metrics(completed_tasks):
    """Generate quality indicator metrics."""
    bug_fixes = len([t for t in completed_tasks if 'bug' in t['type'].lower() or 'fix' in t['title'].lower()])
    feature_work = len([t for t in completed_tasks if any(keyword in t['title'].lower() for keyword in ['add', 'create', 'implement', 'new'])])
    
    if feature_work > 0:
        return f"• **Innovation Focus**: {feature_work} new features delivered, {bug_fixes} stability improvements\n"
    
    return ""

def generate_time_tracking_methodology(time_sources):
    """Generate time tracking methodology section."""
    section = "\n**Time Tracking Methodology**:\n"
    
    if time_sources['jira_logged'] > 0:
        section += f"• {time_sources['jira_logged']} tasks with logged JIRA time (most accurate)\n"
    
    if time_sources['git_estimated'] > 0:
        section += f"• {time_sources['git_estimated']} tasks using enhanced development lifecycle estimation\n"
    
    return section

def generate_enhanced_success_metrics(tasks, business_analysis, completed_tasks, repo_distribution=None):
    """Generate enhanced success metrics with better context."""
    metrics = business_analysis['metrics']
    time_sources = analyze_time_source(tasks)
    
    report = "## SUCCESS METRICS & PERFORMANCE\n"
    
    report += generate_strategic_development_metrics(metrics, completed_tasks)
    report += generate_velocity_metrics(metrics)
    report += generate_repository_metrics(repo_distribution)
    report += generate_pipeline_health_metrics(tasks)
    report += generate_quality_metrics(completed_tasks)
    report += generate_time_tracking_methodology(time_sources)
    
    report += "\n"
    return report

def generate_enhanced_stakeholder_summary(business_analysis, tasks, completed_tasks):
    """Generate an enhanced stakeholder summary with better context and metrics."""
    metrics = business_analysis['metrics']
    
    # Calculate more nuanced completion metrics
    active_development_tasks = len([t for t in tasks if t.get('commits') or t['time'] > 2.0])
    planning_tasks = len(tasks) - active_development_tasks
    
    summary_parts = []
    
    # Executive Overview with Context
    summary_parts.append("## EXECUTIVE SUMMARY")
    summary_parts.append(f"**Development Focus**: {len(completed_tasks)} strategic initiatives completed with {metrics['total_time']:.1f} hours of development investment.")
    
    if planning_tasks > 0:
        summary_parts.append(f"**Pipeline**: {active_development_tasks} active development tasks, {planning_tasks} items in planning/preparation phase.")
    
    # Development Velocity Context
    avg_task_time = metrics['total_time'] / len(completed_tasks) if completed_tasks else 0
    if avg_task_time > 5:
        summary_parts.append(f"**Complexity Profile**: Average {avg_task_time:.1f}h per completed task indicates substantial feature development and architectural work.")
    
    working_days = 22
    daily_intensity = metrics['total_time'] / working_days
    if daily_intensity > 2:
        summary_parts.append(f"**Development Intensity**: {daily_intensity:.1f} hours/day sustained development pace across {working_days} working days.")
    
    return summary_parts

def format_report_header(assignee_name, period_str):
    """Format the main report header."""
    return (f"# DEVELOPMENT IMPACT REPORT\n"
            f"**Developer**: {assignee_name}\n"
            f"**Report Period**: {period_str}\n"
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

def analyze_repository_distribution(tasks):
    """Analyze repository distribution from tasks."""
    repo_distribution = {}
    total_commits = 0
    
    for task in tasks:
        if task.get('repo_sources'):
            for repo_name, commit_count in task['repo_sources'].items():
                if repo_name not in repo_distribution:
                    repo_distribution[repo_name] = {'commits': 0, 'tasks': 0, 'time': 0}
                repo_distribution[repo_name]['commits'] += commit_count
                repo_distribution[repo_name]['tasks'] += 1 if commit_count > 0 else 0
                repo_distribution[repo_name]['time'] += task.get('time', 0)
                total_commits += commit_count
    
    return repo_distribution, total_commits

def analyze_sprint_distribution(tasks):
    """Analyze sprint distribution from tasks."""
    sprint_distribution = {}
    for task in tasks:
        status = task.get('sprint_status', 'Unknown')
        if status not in sprint_distribution:
            sprint_distribution[status] = []
        sprint_distribution[status].append(task)
    return sprint_distribution

def generate_repository_context_section(repo_distribution, total_commits):
    """Generate the repository context section."""
    if len(repo_distribution) <= 1:
        return ""
    
    section = "## REPOSITORY CONTEXT\n"
    sorted_repos = sorted(repo_distribution.items(), key=lambda x: x[1]['commits'], reverse=True)
    
    for repo_name, stats in sorted_repos:
        if stats['commits'] > 0:
            percentage = (stats['commits'] / total_commits * 100) if total_commits > 0 else 0
            section += f"• **{repo_name}**: {stats['commits']} commits, {stats['tasks']} tasks, {stats['time']:.1f}h ({percentage:.1f}% of total commits)\n"
    
    return section + "\n"

def generate_sprint_context_section(sprint_distribution, assignee_name, tasks):
    """Generate the sprint context section."""
    section = "## SPRINT CONTEXT\n"
    
    if sprint_distribution:
        for sprint_status, sprint_tasks in sprint_distribution.items():
            completed_in_sprint = len([t for t in sprint_tasks if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']])
            total_time_in_sprint = sum(t['time'] for t in sprint_tasks if t.get('time', 0) > 0)
            
            if sprint_status == "Closed":
                section += f"• **Closed Sprint Work**: {completed_in_sprint}/{len(sprint_tasks)} tasks completed ({total_time_in_sprint:.1f}h delivered)\n"
            elif sprint_status == "Active":
                section += f"• **Current Sprint**: {completed_in_sprint}/{len(sprint_tasks)} tasks completed ({total_time_in_sprint:.1f}h invested)\n"
            elif sprint_status == "Future":
                section += f"• **Future Sprint**: {len(sprint_tasks)} tasks planned ({total_time_in_sprint:.1f}h estimated)\n"
            else:
                section += f"• **Other Work**: {completed_in_sprint}/{len(sprint_tasks)} tasks ({total_time_in_sprint:.1f}h)\n"
    else:
        section += f"• **Total Work Scope**: {len(tasks)} tasks assigned to {assignee_name}\n"
    
    return section + "\n"

def generate_business_impact_areas_section(business_analysis, assignee_name):
    """Generate the business impact areas section."""
    summary_parts = [f"## KEY BUSINESS IMPACT AREAS - {assignee_name.upper()}"]
    
    categories = business_analysis['categories']
    active_categories = {k: v for k, v in categories.items() if v['tasks']}
    
    impact_highlights = []
    for category_key, category in active_categories.items():
        task_count = len(category['tasks'])
        completed_count = len([t for t in category['tasks'] if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']])
        time_spent = sum(t['time'] for t in category['tasks'] if t['time'] > 0)
        
        if completed_count > 0:  # Only show categories with actual progress
            impact_highlights.append({
                'area': category['impact'],
                'tasks': task_count,
                'completed': completed_count,
                'time': time_spent,
                'completion_rate': (completed_count / task_count * 100) if task_count > 0 else 0
            })
    
    # Sort by completed tasks and time investment
    impact_highlights.sort(key=lambda x: (x['completed'], x['time']), reverse=True)
    
    for highlight in impact_highlights:
        summary_parts.append(f"• **{highlight['area']}**: {highlight['completed']} tasks completed - {highlight['time']:.1f}h development time")
    
    return "\n".join(summary_parts) + "\n\n"

def generate_development_pipeline_section(tasks, completed_tasks):
    """Generate the development pipeline section."""
    if len(tasks) <= len(completed_tasks):
        return ""
    
    pending_high_value = [t for t in tasks if not (t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']) and t.get('time', 0) > 2.0]
    
    if not pending_high_value:
        return ""
    
    section = "\n## DEVELOPMENT PIPELINE\n"
    section += f"**High-Value Items Ready for Development** ({len(pending_high_value)} tasks):\n"
    
    for task in pending_high_value[:5]:  # Top 5 pending items
        sprint_context = f" [{task.get('sprint_status', 'Unknown')} Sprint]" if task.get('sprint_status') != 'Unknown' else ""
        section += f"• {task['title']} ({task['time']:.1f}h estimated){sprint_context}\n"
    
    if len(pending_high_value) > 5:
        section += f"• ... and {len(pending_high_value) - 5} additional items\n"
    
    return section + "\n"

def get_period_string(start_date, end_date):
    """Get formatted period string from date range."""
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        period_str = f"{start_dt.strftime('%B %Y')}"
        if start_dt.month != end_dt.month or start_dt.year != end_dt.year:
            period_str = f"{start_dt.strftime('%B %Y')} - {end_dt.strftime('%B %Y')}"
        return period_str
    except ValueError:
        return f"{start_date} to {end_date}"

def get_assignee_name_from_tasks(tasks):
    """Extract assignee name from tasks."""
    if tasks and tasks[0].get('assignee_email'):
        assignee_email = tasks[0]['assignee_email']
        return assignee_email.split('@')[0].replace('.', ' ').title()
    return "Developer"

def generate_stakeholder_report(tasks, business_analysis, start_date, end_date):
    """Generate a stakeholder-focused report with business value emphasis."""
    
    # Basic report setup
    period_str = get_period_string(start_date, end_date)
    assignee_name = get_assignee_name_from_tasks(tasks)
    completed_tasks = [task for task in tasks if task.get('commits') or task.get('status', '').lower() in ['done', 'closed', 'resolved']]
    
    # Analyze distributions
    repo_distribution, total_commits = analyze_repository_distribution(tasks)
    sprint_distribution = analyze_sprint_distribution(tasks)
    
    # Build report
    report = format_report_header(assignee_name, period_str)
    report += generate_repository_context_section(repo_distribution, total_commits)
    report += generate_sprint_context_section(sprint_distribution, assignee_name, tasks)
    
    # Enhanced Executive Summary with assignee focus
    enhanced_summary = generate_enhanced_stakeholder_summary(business_analysis, tasks, completed_tasks)
    enhanced_summary[0] = f"## EXECUTIVE SUMMARY - {assignee_name.upper()}'S CONTRIBUTIONS"
    
    # Add multi-repo context to executive summary if applicable
    if len(repo_distribution) > 1:
        multi_repo_context = f"**Full-Stack Development**: {total_commits} commits across {len(repo_distribution)} repositories demonstrating comprehensive system knowledge."
        enhanced_summary.insert(1, multi_repo_context)
    
    report += "\n".join(enhanced_summary) + "\n\n"
    
    # AI-Generated Strategic Analysis (if available)
    if len(completed_tasks) > 0:
        ai_summary = generate_summary(tasks)
        if ai_summary and "Business Insights" in ai_summary:
            report += f"## STRATEGIC ANALYSIS - {assignee_name.upper()}'S IMPACT\n"
            report += ai_summary + "\n\n"
    
    # Add remaining sections
    report += generate_business_impact_areas_section(business_analysis, assignee_name)
    report += generate_detailed_impact_analysis(business_analysis['categories'])
    report += generate_enhanced_success_metrics(tasks, business_analysis, completed_tasks, repo_distribution)
    report += generate_sprint_aware_recommendations(tasks, business_analysis['categories'], sprint_distribution)
    report += generate_development_pipeline_section(tasks, completed_tasks)
    
    return report

def extract_action_and_objects(title_lower):
    """Extract action words and object combinations from task title."""
    title_words = title_lower.split()
    action_words = ['add', 'create', 'implement', 'build', 'develop', 'fix', 'update', 'improve', 'enhance', 'optimize']
    object_words = []
    
    for i, word in enumerate(title_words):
        if word in action_words and i + 1 < len(title_words):
            obj = ' '.join(title_words[i+1:i+4])
            if len(obj) > 3:
                object_words.append(f"{word} {obj}")
    
    return object_words

def get_revenue_sales_value(title_lower, object_words):
    """Get business value for Revenue & Sales category."""
    if any(term in title_lower for term in ['discount', 'coupon', 'promo']):
        context = next((obj for obj in object_words if any(term in obj for term in ['discount', 'coupon', 'promo'])), 'promotional system')
        return f"Enhanced promotional capabilities through {context}, driving sales conversion and customer acquisition"
    elif 'cart' in title_lower:
        context = next((obj for obj in object_words if 'cart' in obj), 'shopping cart functionality')
        return f"Improved shopping experience via {context}, reducing cart abandonment and increasing completion rates"
    elif any(term in title_lower for term in ['payment', 'billing', 'checkout']):
        context = next((obj for obj in object_words if any(term in obj for term in ['payment', 'billing', 'checkout'])), 'payment processing')
        return f"Streamlined {context} for better user experience and increased transaction success rates"
    return None

def get_user_experience_value(title_lower, object_words):
    """Get business value for User Experience category."""
    if any(term in title_lower for term in ['login', 'auth', 'session']):
        context = next((obj for obj in object_words if any(term in obj for term in ['login', 'auth', 'session'])), 'authentication system')
        return f"Enhanced user access through {context}, improving security and user experience"
    elif any(term in title_lower for term in ['ui', 'interface', 'design', 'theme']):
        context = next((obj for obj in object_words if any(term in obj for term in ['ui', 'interface', 'design', 'theme'])), 'user interface')
        return f"Improved {context} for better user engagement and platform usability"
    elif any(term in title_lower for term in ['template', 'layout']):
        context = next((obj for obj in object_words if any(term in obj for term in ['template', 'layout'])), 'template system')
        return f"Expanded design capabilities through {context}, providing more user customization options"
    return None

def get_security_compliance_value(title_lower, object_words):
    """Get business value for Security & Compliance category."""
    if any(term in title_lower for term in ['token', 'jwt', 'auth']):
        context = next((obj for obj in object_words if any(term in obj for term in ['token', 'jwt', 'auth'])), 'authentication security')
        return f"Strengthened {context} infrastructure, improving access controls and data protection"
    elif any(term in title_lower for term in ['validation', 'verify']):
        context = next((obj for obj in object_words if any(term in obj for term in ['validation', 'verify'])), 'validation system')
        return f"Enhanced {context} for improved data integrity and security compliance"
    elif any(term in title_lower for term in ['cookie', 'session', 'privacy']):
        context = next((obj for obj in object_words if any(term in obj for term in ['cookie', 'session', 'privacy'])), 'privacy controls')
        return f"Improved {context} for better data handling and regulatory compliance"
    return None

def get_operational_efficiency_value(title_lower, object_words):
    """Get business value for Operational Efficiency category."""
    if 'admin' in title_lower:
        context = next((obj for obj in object_words if 'admin' in obj), 'administrative functionality')
        return f"Enhanced {context} for improved workflow efficiency and system management"
    elif any(term in title_lower for term in ['filter', 'search', 'crud']):
        context = next((obj for obj in object_words if any(term in obj for term in ['filter', 'search', 'crud'])), 'data management tools')
        return f"Improved {context} for enhanced operational productivity and data access"
    elif any(term in title_lower for term in ['automation', 'cron', 'batch']):
        context = next((obj for obj in object_words if any(term in obj for term in ['automation', 'cron', 'batch'])), 'automated processes')
        return f"Implemented {context} to reduce manual overhead and increase operational efficiency"
    return None

def get_platform_stability_value(title_lower, object_words):
    """Get business value for Platform Stability category."""
    if any(term in title_lower for term in ['bug', 'fix', 'error']):
        context = next((obj for obj in object_words if any(term in obj for term in ['bug', 'fix', 'error'])), 'system issues')
        return f"Resolved {context} to improve platform reliability and user experience"
    elif any(term in title_lower for term in ['performance', 'optimize', 'speed']):
        context = next((obj for obj in object_words if any(term in obj for term in ['performance', 'optimize', 'speed'])), 'system performance')
        return f"Optimized {context} for improved responsiveness and user satisfaction"
    elif any(term in title_lower for term in ['storage', 'database', 'cache']):
        context = next((obj for obj in object_words if any(term in obj for term in ['storage', 'database', 'cache'])), 'data infrastructure')
        return f"Enhanced {context} for better system stability and data management"
    return None

def get_feature_expansion_value(title_lower, object_words):
    """Get business value for Feature Expansion category."""
    if any(term in title_lower for term in ['new', 'add', 'create']):
        context = next((obj for obj in object_words if any(term in obj for term in ['new', 'add', 'create'])), 'platform capabilities')
        return f"Expanded {context} to provide additional user value and functionality"
    elif any(term in title_lower for term in ['implement', 'develop', 'build']):
        context = next((obj for obj in object_words if any(term in obj for term in ['implement', 'develop', 'build'])), 'new functionality')
        return f"Delivered {context} to enhance platform offerings and user experience"
    return None

def extract_specific_business_value(task_title, category):
    """Extract specific business value from task titles with more detailed analysis."""
    title_lower = task_title.lower()
    object_words = extract_action_and_objects(title_lower)
    
    # Category-specific transformations
    category_handlers = {
        "Revenue & Sales": get_revenue_sales_value,
        "User Experience": get_user_experience_value,
        "Security & Compliance": get_security_compliance_value,
        "Operational Efficiency": get_operational_efficiency_value,
        "Platform Stability": get_platform_stability_value,
        "Feature Expansion": get_feature_expansion_value
    }
    
    handler = category_handlers.get(category)
    if handler:
        result = handler(title_lower, object_words)
        if result:
            return result
    
    # Enhanced fallback with more context
    cleaned_title = task_title.replace("TD-", "").replace("SSW-", "").replace("PROJ-", "")
    if object_words:
        main_work = object_words[0]
        return f"Completed {main_work} to enhance platform capabilities and business value"
    else:
        return f"Delivered {cleaned_title.lower()} to improve platform functionality and user experience"

def transform_revenue_sales_value(title_lower):
    """Transform revenue and sales task titles to business value."""
    if "discount" in title_lower or "coupon" in title_lower:
        return "Enhanced promotional capabilities to drive sales conversion"
    elif "cart" in title_lower:
        return "Improved shopping experience to reduce cart abandonment"
    elif "payment" in title_lower or "billing" in title_lower:
        return "Streamlined payment processing for better user experience"
    return None

def transform_user_experience_value(title_lower):
    """Transform user experience task titles to business value."""
    if "login" in title_lower or "session" in title_lower:
        return "Improved user authentication and session management"
    elif "thumbnail" in title_lower or "theme" in title_lower:
        return "Enhanced visual presentation and user interface"
    elif "template" in title_lower:
        return "Expanded design options for better user engagement"
    return None

def transform_security_compliance_value(title_lower):
    """Transform security and compliance task titles to business value."""
    if "token" in title_lower or "auth" in title_lower:
        return "Strengthened security infrastructure and access controls"
    elif "validation" in title_lower:
        return "Enhanced data validation and security measures"
    elif "cookie" in title_lower:
        return "Improved secure data handling and privacy compliance"
    return None

def transform_operational_efficiency_value(title_lower):
    """Transform operational efficiency task titles to business value."""
    if "admin" in title_lower:
        return "Enhanced administrative capabilities and workflow efficiency"
    elif "filter" in title_lower or "crud" in title_lower:
        return "Improved data management and operational tools"
    elif "cron" in title_lower or "automation" in title_lower:
        return "Automated processes to reduce manual overhead"
    return None

def transform_platform_stability_value(title_lower):
    """Transform platform stability task titles to business value."""
    if "bug" in title_lower or "fix" in title_lower:
        return "Resolved critical issues to improve system reliability"
    elif "error" in title_lower:
        return "Enhanced error handling and user experience"
    elif "performance" in title_lower:
        return "Optimized system performance and responsiveness"
    return None

def transform_feature_expansion_value(title_lower):
    """Transform feature expansion task titles to business value."""
    if "new" in title_lower or "add" in title_lower:
        return "Expanded platform capabilities and user options"
    elif "implement" in title_lower or "create" in title_lower:
        return "Delivered new functionality to enhance user value"
    return None

def transform_to_business_value(technical_title, category):
    """Transform technical task titles into business value statements."""
    
    # Try enhanced extraction first
    enhanced_value = extract_specific_business_value(technical_title, category)
    if enhanced_value:
        return enhanced_value
    
    # Fallback to original transformation functions
    title_lower = technical_title.lower()
    
    transformation_functions = {
        "Revenue & Sales": transform_revenue_sales_value,
        "User Experience": transform_user_experience_value,
        "Security & Compliance": transform_security_compliance_value,
        "Operational Efficiency": transform_operational_efficiency_value,
        "Platform Stability": transform_platform_stability_value,
        "Feature Expansion": transform_feature_expansion_value
    }
    
    transform_func = transformation_functions.get(category)
    if transform_func:
        result = transform_func(title_lower)
        if result:
            return result
    
    # Final fallback
    return technical_title.replace("TD-", "").replace("Add ", "Added ").replace("Fix ", "Fixed ").replace("Update ", "Updated ")

def generate_detailed_impact_analysis(categories):
    """Generate the detailed impact analysis section of the report."""
    report = "## DETAILED IMPACT ANALYSIS\n\n"
    
    for category_key, category in categories.items():
        if not category['tasks']:
            continue
            
        report += f"### {category['impact']}\n"
        
        # Category summary
        completed = len([t for t in category['tasks'] if t.get('commits')])
        total = len(category['tasks'])
        time_invested = sum(t['time'] for t in category['tasks'] if t['time'] > 0)
        
        report += f"**Status**: {completed}/{total} completed | **Time Investment**: {time_invested:.1f} hours\n\n"
        
        # Key achievements
        completed_tasks = [t for t in category['tasks'] if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']]
        if completed_tasks:
            report += "**Key Achievements**:\n"
            for task in completed_tasks[:3]:  # Top 3 completed tasks
                # Transform technical title to business value
                business_value = transform_to_business_value(task['title'], category['impact'])
                report += f"• {business_value}\n"
            
            if len(completed_tasks) > 3:
                report += f"• ... and {len(completed_tasks) - 3} additional improvements\n"
        
        # Pending items
        pending_tasks = [t for t in category['tasks'] if not t.get('commits')]
        if pending_tasks:
            report += f"\n**Pending Items** ({len(pending_tasks)} tasks): Strategic initiatives ready for next phase\n"
        
        report += "\n"
    
    return report

def analyze_sprint_progress(sprint_distribution):
    """Analyze current sprint progress."""
    recommendations = []
    
    active_sprint_tasks = sprint_distribution.get('Active', [])
    if active_sprint_tasks:
        active_completed = len([t for t in active_sprint_tasks if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']])
        active_pending = len(active_sprint_tasks) - active_completed
        if active_pending > 0:
            recommendations.append(f"• **Current Sprint Focus**: {active_pending} tasks remaining in active sprint (priority completion)")
    
    return recommendations

def analyze_pending_priorities(tasks):
    """Analyze pending high-priority tasks."""
    recommendations = []
    
    uncompleted = [t for t in tasks if not (t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved'])]
    high_value_pending = [t for t in uncompleted if t.get('time', 0) > 3.0]
    
    if high_value_pending:
        recommendations.append(f"• **Priority Development**: {len(high_value_pending)} high-value items ready for next sprint")
    
    return recommendations

def analyze_category_recommendations(categories):
    """Analyze category-based strategic recommendations."""
    recommendations = []
    
    revenue_pending = [t for t in categories['revenue_generation']['tasks'] if not (t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved'])]
    if revenue_pending:
        revenue_time = sum(t['time'] for t in revenue_pending)
        recommendations.append(f"• **Revenue Acceleration**: {len(revenue_pending)} revenue-impacting features ({revenue_time:.1f}h investment) in development pipeline")
    
    security_pending = [t for t in categories['security_compliance']['tasks'] if not (t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved'])]
    if security_pending:
        recommendations.append(f"• **Security Roadmap**: {len(security_pending)} security enhancements planned for implementation")
    
    return recommendations

def analyze_velocity_insights(tasks):
    """Analyze development velocity insights."""
    recommendations = []
    
    completed_tasks = [t for t in tasks if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']]
    if len(completed_tasks) >= 3:
        avg_completion_time = sum(t['time'] for t in completed_tasks) / len(completed_tasks)
        estimated_sprint_capacity = (10 * 5) / avg_completion_time  # Assuming 2-week sprint, 5h/day
        recommendations.append(f"• **Sprint Planning**: Based on current complexity, estimated capacity of {estimated_sprint_capacity:.0f}-{estimated_sprint_capacity*1.2:.0f} similar tasks per sprint")
    
    return recommendations

def analyze_sprint_performance(sprint_distribution):
    """Analyze sprint completion performance."""
    recommendations = []
    
    closed_sprint_tasks = sprint_distribution.get('Closed', [])
    if closed_sprint_tasks:
        closed_completed = len([t for t in closed_sprint_tasks if t.get('commits') or t.get('status', '').lower() in ['done', 'closed', 'resolved']])
        closed_completion_rate = (closed_completed / len(closed_sprint_tasks) * 100) if closed_sprint_tasks else 0
        recommendations.append(f"• **Sprint Performance**: {closed_completion_rate:.1f}% completion rate in closed sprints demonstrates consistent delivery")
    
    return recommendations

def generate_sprint_aware_recommendations(tasks, categories, sprint_distribution):
    """Generate sprint-aware recommendations section."""
    report = "## STRATEGIC RECOMMENDATIONS\n"
    
    all_recommendations = []
    all_recommendations.extend(analyze_sprint_progress(sprint_distribution))
    all_recommendations.extend(analyze_pending_priorities(tasks))
    all_recommendations.extend(analyze_category_recommendations(categories))
    all_recommendations.extend(analyze_velocity_insights(tasks))
    all_recommendations.extend(analyze_sprint_performance(sprint_distribution))
    
    for recommendation in all_recommendations:
        report += recommendation + "\n"
    
    report += "• **Development Excellence**: Strong foundation established for continued feature development and platform enhancement\n\n"
    
    return report

def generate_recommendations_section(tasks, categories):
    """Generate the next phase recommendations section (fallback function)."""
    # This is kept for backward compatibility
    return generate_sprint_aware_recommendations(tasks, categories, {})

def generate_enhanced_business_summary(tasks, completed_tasks):
    """Generate an enhanced business summary without AI that provides specific insights."""
    if not completed_tasks:
        return NO_TASKS_COMPLETED_MESSAGE
    
    # Calculate metrics
    total_time = sum(task['time'] for task in tasks if task['time'] > 0)
    
    # Analyze completed work for patterns
    feature_keywords = ['feature', 'add', 'new', 'implement', 'create']
    improvement_keywords = ['fix', 'improve', 'update', 'enhance', 'optimize']
    security_keywords = ['security', 'auth', 'token', 'validation', 'access']
    
    feature_work = []
    improvements = []
    security_work = []
    
    for task in completed_tasks:
        title_lower = task['title'].lower()
        if any(keyword in title_lower for keyword in feature_keywords):
            feature_work.append(task)
        elif any(keyword in title_lower for keyword in improvement_keywords):
            improvements.append(task)
        elif any(keyword in title_lower for keyword in security_keywords):
            security_work.append(task)
    
    # Build specific summary
    summary_parts = []
    
    # Overview
    working_days = 22
    daily_avg = total_time / working_days
    summary_parts.append(f"Delivered {len(completed_tasks)} development initiatives with {total_time:.1f} hours of professional development work ({daily_avg:.1f}h/day average).")
    
    # Specific achievements
    if feature_work:
        feature_time = sum(t['time'] for t in feature_work)
        summary_parts.append(f"New capabilities: {len(feature_work)} features developed ({feature_time:.1f}h investment), expanding platform functionality.")
    
    if improvements:
        improvement_time = sum(t['time'] for t in improvements)
        summary_parts.append(f"Platform enhancement: {len(improvements)} improvements implemented ({improvement_time:.1f}h investment), strengthening system reliability.")
    
    if security_work:
        security_time = sum(t['time'] for t in security_work)
        summary_parts.append(f"Security advancement: {len(security_work)} security enhancements ({security_time:.1f}h investment), improving system protection.")
    
    # Development velocity insight
    if len(completed_tasks) >= 3:
        avg_task_time = total_time / len(completed_tasks)
        if avg_task_time > 8:
            summary_parts.append(f"Development pattern: Complex feature work averaging {avg_task_time:.1f}h per task, indicating substantial technical implementations.")
        elif avg_task_time < 3:
            summary_parts.append(f"Development pattern: Efficient task completion averaging {avg_task_time:.1f}h per task, showing optimized development velocity.")
        else:
            summary_parts.append(f"Development pattern: Balanced development approach averaging {avg_task_time:.1f}h per task, maintaining steady delivery pace.")
    
    return " ".join(summary_parts)

def parse_repository_arguments(args):
    """Parse and validate repository path arguments."""
    repo_paths = []
    if args.repos:
        repo_paths = [path.strip() for path in args.repos.split(',')]
        print(f"🔧 Multi-repository mode: {len(repo_paths)} repositories")
        for i, path in enumerate(repo_paths, 1):
            print(f"   {i}. {path}")
    else:
        print("❌ Error: Must specify --repos")
        return None
    
    return repo_paths

def validate_repositories(repo_paths):
    """Validate that all repository paths are valid git repositories."""
    valid_repos = []
    for repo_path in repo_paths:
        try:
            git.Repo(repo_path)  # Just validate, don't store the repo object
            valid_repos.append(repo_path)
            print(f"✅ Valid repository: {repo_path}")
        except Exception as e:
            print(f"⚠️ Invalid repository {repo_path}: {e}")
    
    if not valid_repos:
        print("❌ Error: No valid repositories found")
        return None
    
    return valid_repos

def process_task_commits(tasks, repo_paths, start_date, end_date):
    """Process commits for all tasks across multiple repositories."""
    print(f"\n🔍 Analyzing commits across {len(repo_paths)} repositories...")
    
    for task in tasks:
        print(f"\n📋 Task {task['id']}: {task['title'][:60]}...")
        
        if len(repo_paths) == 1:
            repo = git.Repo(repo_paths[0])
            commits = fetch_commits(repo, task['id'], start_date, end_date)
            task['commits'] = commits
            task['repo_sources'] = {repo_paths[0].split('/')[-1]: len(commits)} if commits else {}
        else:
            commits, repo_sources = fetch_commits_from_multiple_repos(repo_paths, task['id'], start_date, end_date)
            task['commits'] = commits
            task['repo_sources'] = repo_sources
        
        task['time'] = get_final_time_estimate(task, task['commits'])

def generate_report_content(args, tasks, business_analysis, start_date, end_date):
    """Generate the appropriate report content based on arguments."""
    if args.report_type == 'stakeholder':
        return generate_stakeholder_report(tasks, business_analysis, start_date, end_date)
    elif args.report_type == 'technical':
        summary = generate_summary(tasks)
        return build_report(tasks, summary)
    else:  # both
        stakeholder_report = generate_stakeholder_report(tasks, business_analysis, start_date, end_date)
        summary = generate_summary(tasks)
        technical_report = build_report(tasks, summary)
        return stakeholder_report + "\n\n" + "="*80 + "\n\n" + "# TECHNICAL DETAILS REPORT\n\n" + technical_report

def output_report_summary(args, business_analysis, tasks):
    """Output a summary of the generated report to console."""
    print(f"Report type: {args.report_type}")
    print(f"Format: {args.format}")
    
    print("\n📊 REPORT SUMMARY:")
    print(f"   • Total tasks analyzed: {business_analysis['metrics']['total_tasks']}")
    print(f"   • Tasks completed: {business_analysis['metrics']['completed_tasks']}")
    print(f"   • Completion rate: {business_analysis['metrics']['completion_rate']:.1f}%")
    print(f"   • Total time tracked: {business_analysis['metrics']['total_time']:.1f} hours")
    print(f"   • High priority items: {business_analysis['metrics']['high_priority_tasks']}")
    
    print("\n📁 REPOSITORY CONTRIBUTIONS:")
    repo_totals = {}
    for task in tasks:
        if task.get('repo_sources'):
            for repo_name, commit_count in task['repo_sources'].items():
                if repo_name not in repo_totals:
                    repo_totals[repo_name] = {'commits': 0, 'tasks': 0}
                repo_totals[repo_name]['commits'] += commit_count
                repo_totals[repo_name]['tasks'] += 1
    
    for repo_name, stats in repo_totals.items():
        print(f"   • {repo_name}: {stats['commits']} commits across {stats['tasks']} tasks")

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Generate a work report with AI summary.")
    parser.add_argument("--assignee", required=True, help="Jira assignee username")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--repos", required=True, help="Comma-separated paths to Git repositories (e.g., '/path/repo1,/path/repo2,/path/repo3')")
    parser.add_argument("--output", help="Output file path for the report (optional)")
    parser.add_argument("--report-type", 
                        choices=['technical', 'stakeholder', 'both'], 
                        default='stakeholder',
                        help="Type of report to generate (default: stakeholder)")
    parser.add_argument("--format", 
                        choices=['markdown', 'text'], 
                        default='markdown',
                        help="Output format (default: markdown)")
    args = parser.parse_args()

    # Handle repository paths
    repo_paths = parse_repository_arguments(args)
    if not repo_paths:
        return

    # Validate repository paths
    repo_paths = validate_repositories(repo_paths)
    if not repo_paths:
        return

    # Initialize Jira client
    jira = JIRA(server=os.getenv("JIRA_URL"), basic_auth=(os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN")))

    # Fetch tasks from Jira
    tasks = fetch_tasks(jira, args.assignee, args.start_date, args.end_date)

    # Process commits for each task
    process_task_commits(tasks, repo_paths, args.start_date, args.end_date)

    # Analyze business impact
    business_analysis = analyze_business_impact(tasks)

    # Generate report
    report = generate_report_content(args, tasks, business_analysis, args.start_date, args.end_date)

    # Output the report
    if args.output:
        try:
            with open(args.output, 'w') as f:
                f.write(report)
            print(f"Report saved to {args.output}")
            output_report_summary(args, business_analysis, tasks)
        except IOError as e:
            print(f"Error writing to file: {e}")
    else:
        print(report)

if __name__ == "__main__":
    main()