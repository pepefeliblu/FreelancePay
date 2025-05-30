# FreelancePay - Professional Development Reports

A comprehensive tool for generating professional development reports by analyzing JIRA tasks and Git commits. Perfect for freelancers, contractors, and development teams who need to create detailed, visually appealing reports for stakeholders.

## ✨ Features

### 📊 Professional Visualizations
- **Business Impact Charts**: Interactive pie charts and bar graphs showing time investment by category
- **Performance Dashboards**: KPI indicators, completion rates, and velocity metrics
- **Development Trends**: Weekly progress tracking and velocity analysis
- **Repository Activity**: Multi-repository commit and time distribution analysis
- **Priority Distribution**: Task priority breakdown with visual indicators

### 📄 Multiple Export Formats
- **Markdown**: Standard text format for developers
- **DOCX**: Professional Word documents with embedded charts
- **PDF**: Publication-ready reports with styling and graphics
- **All Formats**: Generate complete report package in one command

### 🎯 Stakeholder-Ready Reports
- Executive summaries with business impact analysis
- Strategic development metrics and ROI insights
- Multi-repository contribution tracking
- AI-powered business insights (OpenAI/Gemini integration)
- Professional styling and corporate-ready layouts

## 🚀 Quick Start

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/pepefeliblu/FreelancePay
   cd FreelancePay
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your credentials
   ```

### Basic Usage

**Generate a comprehensive professional report package:**
```bash
python main.py \
  --assignee "your.email@company.com" \
  --start-date "2024-01-01" \
  --end-date "2024-01-31" \
  --repos "/path/to/repo1,/path/to/repo2" \
  --format all \
  --charts
```

**Generate stakeholder report with charts in PDF:**
```bash
python main.py \
  --assignee "developer@company.com" \
  --start-date "2024-01-01" \
  --end-date "2024-01-31" \
  --repos "/path/to/repository" \
  --format pdf \
  --charts \
  --report-type stakeholder
```

**Generate technical report with visualizations:**
```bash
python main.py \
  --assignee "dev.team@company.com" \
  --start-date "2024-01-01" \
  --end-date "2024-01-31" \
  --repos "/path/to/repo" \
  --format docx \
  --charts \
  --report-type technical
```

## 📈 Report Types & Visualizations

### Stakeholder Reports
Perfect for project managers, tech leads, and business stakeholders:

- **Executive Summary**: High-level business impact and metrics
- **Business Impact Analysis**: Categorized by Revenue, UX, Security, etc.
- **Strategic Development Metrics**: Velocity, complexity, and ROI analysis
- **Success Metrics Dashboard**: KPIs, completion rates, and performance indicators
- **Professional Charts**: 
  - Business impact distribution (pie charts)
  - Development velocity trends (line graphs)
  - Repository activity analysis (bar charts)
  - Performance dashboard (gauges and indicators)

### Technical Reports
Detailed for development teams and technical audiences:

- **Detailed Task Breakdown**: Individual task analysis with commits
- **Repository Context**: Multi-repo contribution tracking
- **Time Tracking Analysis**: JIRA time vs. estimated time comparison
- **Sprint Integration**: Sprint-aware reporting and planning insights

## 🎨 Chart Types Generated

### 1. Business Impact Analysis
- **Time Investment Pie Chart**: Shows hours spent by business category
- **Task Completion Bar Chart**: Compares total vs completed tasks by category
- **Color-coded by Category**: Revenue (Blue), UX (Purple), Security (Orange), etc.

### 2. Performance Dashboard
- **Completion Rate Gauge**: Visual indicator of project completion percentage
- **Total Hours Indicator**: Summary metric with delta comparison
- **Weekly Progress Lines**: Planned vs actual progress tracking
- **Task Status Distribution**: Pie chart of completed vs in-progress tasks

### 3. Development Velocity Trends
- **Hours per Week**: Line chart showing development intensity over time
- **Tasks per Week**: Completion velocity tracking
- **Trend Analysis**: Visual patterns in development pace

### 4. Repository Activity
- **Commits per Repository**: Bar chart showing contribution distribution
- **Hours per Repository**: Time investment across multiple codebases
- **Multi-repo Context**: Understanding of full-stack development scope

### 5. Priority Distribution
- **Task Priority Breakdown**: Bar chart of High/Medium/Low priority tasks
- **Color-coded Priorities**: Visual priority assessment
- **Resource Allocation Insights**: Understanding of priority focus

## 🔧 Command Line Options

```bash
python main.py [OPTIONS]

Required:
  --assignee EMAIL          JIRA assignee email/username
  --start-date YYYY-MM-DD   Report start date
  --end-date YYYY-MM-DD     Report end date  
  --repos PATHS             Comma-separated repository paths

Optional:
  --output FILE             Output file path
  --report-type TYPE        Report type: technical|stakeholder|both (default: stakeholder)
  --format FORMAT           Output format: markdown|text|docx|pdf|all (default: markdown)
  --charts                  Generate professional charts and visualizations
```

## 📊 Professional Features

### Chart Styling
- **Corporate Color Palette**: Professional blue, purple, orange color scheme
- **High-Resolution Export**: 2x scale factor for crisp presentation graphics
- **Responsive Design**: Charts optimized for both digital and print media
- **Brand Consistency**: Consistent styling across all visualization types

### Document Formatting
- **DOCX Features**:
  - Professional document structure with proper headings
  - Embedded high-resolution charts
  - Styled bullet points and formatting
  - Corporate-ready layout
  
- **PDF Features**:
  - Publication-quality typography
  - Embedded charts as base64 images
  - Professional CSS styling
  - Print-optimized layout

### Business Intelligence
- **Automated Categorization**: AI-powered business impact classification
- **ROI Analysis**: Time investment vs business value correlation
- **Strategic Insights**: Pattern recognition in development activities
- **Stakeholder Language**: Business-friendly terminology and metrics

## 🛠 Configuration

### Environment Variables (.env)
```bash
# Required
JIRA_URL=https://yourcompany.atlassian.net
JIRA_USERNAME=your.email@company.com
JIRA_API_TOKEN=your_api_token

# Optional (for AI summaries)
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
```

### Dependencies
The tool automatically handles missing dependencies:
- **Core Features**: JIRA integration, Git analysis, basic reporting
- **Advanced Features**: Chart generation, DOCX/PDF export require additional packages
- **Graceful Degradation**: Falls back to markdown if advanced packages unavailable

## 📈 Sample Output

### Generated Files
When using `--format all`, you'll get:
```
reports/
├── john_doe_20240131_143022.docx    # Professional Word document
├── john_doe_20240131_143022.pdf     # Publication-ready PDF
├── john_doe_20240131_143022.md      # Markdown source
└── charts/
    ├── business_impact.png          # Business category analysis
    ├── performance_dashboard.png    # KPI dashboard
    ├── velocity_trends.png          # Development velocity
    ├── repository_activity.png     # Multi-repo analysis
    └── priority_distribution.png   # Task priority breakdown
```

### Professional Report Sections
1. **Executive Summary** - High-level business impact
2. **Strategic Analysis** - AI-powered insights
3. **Business Impact Areas** - Categorized achievements
4. **Performance Metrics** - KPIs and success indicators
5. **Visual Analytics** - Professional charts and graphs
6. **Strategic Recommendations** - Future planning insights

## 🎯 Use Cases

### For Freelancers
- Client-ready professional reports
- Visual proof of business impact
- Time tracking with business value correlation
- Multiple format support for different client preferences

### For Development Teams
- Sprint retrospectives with visual analytics
- Stakeholder communication with business language
- Multi-repository contribution tracking
- Performance trend analysis

### For Project Managers
- Executive dashboard creation
- Resource allocation insights
- ROI analysis and business case building
- Professional presentation materials

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new chart types or export formats
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

**FreelancePay** - Transform your development work into professional, stakeholder-ready reports with comprehensive analytics and beautiful visualizations.