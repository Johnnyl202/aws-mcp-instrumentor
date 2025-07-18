"""
CloudWatch AI Agent - Strands Agent for Alarm-Based Troubleshooting

This agent focuses on troubleshooting CloudWatch alarms by:
- Identifying active alarms and their historical patterns
- Retrieving related metrics and logs for analysis
- Analyzing alarm patterns to determine root causes
- Providing context-aware recommendations for remediation

The agent uses the CloudWatch MCP server to access AWS CloudWatch resources.
"""

import os
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from strands import Agent
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class CloudWatchAIAgent:
    """CloudWatch AI Agent for alarm-based troubleshooting."""
    
    def __init__(self, model_id: Optional[str] = None):
        """Initialize the CloudWatch AI Agent.
        
        Args:
            model_id: Optional model ID to use for the agent. 
                     Defaults to Claude 3.7 Sonnet on Bedrock.
        """
        self.model_id = model_id
        self.agent = None
        self.mcp_client = None
        self._setup_mcp_client()
    
    def _setup_mcp_client(self):
        """Set up the MCP client for CloudWatch server connection."""
        # Create MCP client for CloudWatch server using Docker transport
        self.mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command="opentelemetry-instrument",
                args=["python3", "mcpserver.py"],
                env={
                    "OTEL_TRACES_EXPORTER": "otlp",
                    "OTEL_RESOURCE_ATTRIBUTES": "service.name=AppSignals MCP Server",
                    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "https://xray.us-east-1.amazonaws.com/v1/traces",
                    "OTEL_LOGS_EXPORTER": "none",
                    "OTEL_METRICS_EXPORTER": "none",
                    "OTEL_PYTHON_DISTRO": "aws_distro",
                    "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
                    "OTEL_TRACES_SAMPLER": "always_on"
                }
            )
        ))
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for alarm troubleshooting."""
        return """You are a CloudWatch AI Agent specialized in alarm-based troubleshooting. Your primary role is to help users diagnose and resolve CloudWatch alarm issues by:

**Core Capabilities:**
1. **Active Alarm Analysis**: Identify currently active alarms and their severity
2. **Historical Pattern Recognition**: Analyze alarm history to identify patterns, trends, and recurring issues
3. **Metric & Log Correlation**: Retrieve and analyze related metrics and logs to understand root causes
4. **Context-Aware Recommendations**: Provide specific, actionable remediation steps based on analysis

**Troubleshooting Approach:**
1. **Discovery Phase**: Start by identifying active alarms and their current state
2. **Analysis Phase**: Examine alarm history, related metrics, and associated logs
3. **Pattern Recognition**: Look for patterns like alarm flapping, time-based triggers, or resource correlations
4. **Root Cause Analysis**: Correlate metrics, logs, and alarm patterns to identify underlying issues
5. **Remediation Guidance**: Provide specific, prioritized recommendations for resolution

**Available Tools:**
- `get_active_alarms`: Get all currently active (ALARM state) alarms
- `get_alarm_history`: Retrieve alarm state change history and get investigation time ranges
- `analyze_log_group`: Analyze log groups for anomalies and error patterns
- `get_metric_data`: Retrieve metric data for analysis
- `execute_log_insights_query`: Query logs for specific patterns or issues
- `describe_log_groups`: Discover available log groups

**Best Practices:**
- Always start with active alarms to understand current issues
- Use alarm history to identify patterns and get suggested investigation timeframes
- Correlate metrics with alarm triggers to understand causation
- Look for related log entries during alarm periods
- Provide prioritized recommendations based on severity and impact
- Suggest both immediate fixes and long-term preventive measures

**Communication Style:**
- Be clear and structured in your analysis
- Provide step-by-step troubleshooting workflows
- Include relevant data and evidence in your recommendations
- Explain technical concepts in accessible terms
- Prioritize recommendations by urgency and impact

Remember: Your goal is to help users quickly identify, understand, and resolve CloudWatch alarm issues through systematic analysis and evidence-based recommendations."""

    def start_session(self) -> Agent:
        """Start a new troubleshooting session with the CloudWatch AI Agent.
        
        Returns:
            The initialized Strands Agent with CloudWatch MCP tools.
            
        Raises:
            Exception: If MCP client setup fails or tools cannot be loaded.
        """
        try:
            # Get tools from the MCP server
            tools = self.mcp_client.list_tools_sync()
            logger.info(f"Loaded {len(tools)} CloudWatch MCP tools")
            
            # Create the agent with CloudWatch tools
            self.agent = Agent(
                model=self.model_id,
                tools=tools,
                system_prompt=self._get_system_prompt(),
                name="CloudWatch AI Agent",
                description="Specialized agent for CloudWatch alarm troubleshooting and analysis"
            )
            
            logger.info("CloudWatch AI Agent initialized successfully")
            return self.agent
            
        except Exception as e:
            logger.error(f"Failed to initialize CloudWatch AI Agent: {e}")
            raise
    
    def troubleshoot(self, issue_description: str) -> str:
        """Troubleshoot a CloudWatch alarm issue.
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call start_session() first.")
        
        # Create a comprehensive troubleshooting prompt
        prompt = f"""I need help troubleshooting a CloudWatch alarm issue:

**Issue Description:** {issue_description}

Please help me with a comprehensive analysis:

1. **Active Alarm Assessment**: Check what alarms are currently active and their status
2. **Historical Analysis**: Review alarm history to identify patterns or recent changes  
3. **Metric Analysis**: Examine related metrics during alarm periods
4. **Log Investigation**: Check associated logs for errors or anomalies during alarm periods
5. **Root Cause Analysis**: Correlate findings to identify likely root causes
6. **Remediation Plan**: Provide prioritized, actionable recommendations

Please start with the active alarms and work systematically through the analysis."""

        try:
            result = self.agent(prompt)
            formatted_result = OutputFormatter.format_output(str(result))
            return formatted_result
        except Exception as e:
            logger.error(f"Troubleshooting failed: {e}")
            return f"Troubleshooting encountered an error: {e}"
    
    def analyze_specific_alarm(self, alarm_name: str, time_range_hours: int = 24) -> str:
        """Analyze a specific alarm in detail.
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call start_session() first.")
        
        prompt = f"""Please provide a detailed analysis of the alarm '{alarm_name}':

1. **Current Status**: Check if this alarm is currently active
2. **Historical Analysis**: Review the last {time_range_hours} hours of alarm history
3. **Pattern Recognition**: Identify any patterns in alarm state changes
4. **Metric Correlation**: Analyze the underlying metrics that trigger this alarm
5. **Log Analysis**: Check related logs during alarm periods for errors or anomalies
6. **Recommendations**: Provide specific recommendations for this alarm

Focus on providing actionable insights and specific remediation steps."""

        try:
            result = self.agent(prompt)
            formatted_result = OutputFormatter.format_output(str(result))
            return formatted_result
        except Exception as e:
            logger.error(f"Alarm analysis failed: {e}")
            return f"Alarm analysis encountered an error: {e}"
    
    def get_alarm_insights(self) -> str:
        """Get general insights about the current alarm state.
        
        Returns:
            General insights about active alarms and overall system health
        """
        if not self.agent:
            raise RuntimeError("Agent not initialized. Call start_session() first.")
        
        prompt = """Please provide an overview of the current CloudWatch alarm status:

1. **Active Alarm Summary**: List all currently active alarms with their key details
2. **Severity Assessment**: Categorize alarms by severity/impact
3. **Pattern Analysis**: Identify any concerning patterns across multiple alarms
4. **System Health Overview**: Provide a general assessment of system health based on alarm status
5. **Priority Recommendations**: Suggest which alarms should be addressed first

This should give me a high-level view of what needs attention right now."""

        try:
            result = self.agent(prompt)
            formatted_result = OutputFormatter.format_output(str(result))
            return formatted_result
        except Exception as e:
            logger.error(f"Alarm insights failed: {e}")
            return f"Alarm insights encountered an error: {e}"
    
    def __enter__(self):
        """Context manager entry."""
        self.mcp_client.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.mcp_client:
            self.mcp_client.__exit__(exc_type, exc_val, exc_tb)


def main():
    """Example usage of the CloudWatch AI Agent."""
    import argparse
    
    parser = argparse.ArgumentParser(description="CloudWatch AI Agent for Alarm Troubleshooting")
    parser.add_argument("--model", help="Model ID to use (default: Claude 3.7 Sonnet)")
    parser.add_argument("--issue", help="Describe the alarm issue you're experiencing")
    parser.add_argument("--alarm", help="Specific alarm name to analyze")
    parser.add_argument("--insights", action="store_true", help="Get general alarm insights")
    
    args = parser.parse_args()
    
    # Use the agent within context manager
    with CloudWatchAIAgent(model_id=args.model) as agent:
        # Start the session
        strands_agent = agent.start_session()
        
        if args.insights:
            print("=== CloudWatch Alarm Insights ===")
            print(agent.get_alarm_insights())
        elif args.alarm:
            print(f"=== Analysis of Alarm: {args.alarm} ===")
            print(agent.analyze_specific_alarm(args.alarm))
        elif args.issue:
            print("=== CloudWatch Troubleshooting Analysis ===")
            print(agent.troubleshoot(args.issue))
        else:
            # Interactive mode
            print("CloudWatch AI Agent - Interactive Mode")
            print("Available commands:")
            print("- 'insights': Get general alarm insights")
            print("- 'analyze <alarm_name>': Analyze specific alarm")
            print("- 'help <issue_description>': Get troubleshooting help")
            print("- 'quit': Exit")
            
            while True:
                try:
                    user_input = input("\n> ").strip()
                    
                    if user_input.lower() == 'quit':
                        break
                    elif user_input.lower() == 'insights':
                        result = agent.get_alarm_insights()
                        print(result)
                    elif user_input.lower().startswith('analyze '):
                        alarm_name = user_input[8:].strip()
                        result = agent.analyze_specific_alarm(alarm_name)
                        print(result)
                    elif user_input.lower().startswith('help '):
                        issue = user_input[5:].strip()
                        result = agent.troubleshoot(issue)
                        print(result)
                    else:
                        print("Unknown command. Type 'quit' to exit.")
                        
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
                except Exception as e:
                    print(f"Error: {e}")


class OutputFormatter:
    """Utility class for formatting agent outputs with background colors."""
    
    # ANSI color codes for background colors
    STEP_BG = '\033[48;5;22m'         # Green background for all steps
    MCP_TOOL_BG = '\033[48;5;94m'     # Orange/brown background for MCP tool calls
    RESET = '\033[0m'                 # Reset all formatting
    WHITE_TEXT = '\033[97m'           # White text for better contrast
    
    # Common MCP tool names for CloudWatch
    MCP_TOOLS = [
        'get_active_alarms',
        'get_alarm_history', 
        'analyze_log_group',
        'get_metric_data',
        'execute_log_insights_query',
        'describe_log_groups'
    ]
    
    @classmethod
    def format_output(cls, text: str) -> str:
        """Format agent output with background colors for steps and MCP tool calls.
        
        Args:
            text: Raw agent output text
            
        Returns:
            Formatted text with colored backgrounds
        """
        if not text:
            return text
            
        # Split into lines for processing
        lines = text.split('\n')
        formatted_lines = []
        
        for line in lines:
            formatted_line = line
            
            # Check if this line contains a step marker (numbered steps, bullets, etc.)
            if cls._is_step_line(line):
                formatted_line = f"{cls.STEP_BG}{cls.WHITE_TEXT}{line}{cls.RESET}"
            
            # Check if this line mentions MCP tools
            elif cls._contains_mcp_tool(line):
                formatted_line = f"{cls.MCP_TOOL_BG}{cls.WHITE_TEXT}{line}{cls.RESET}"
            
            formatted_lines.append(formatted_line)
        
        return '\n'.join(formatted_lines)
    
    @classmethod
    def _is_step_line(cls, line: str) -> bool:
        """Check if a line represents a step in the analysis."""
        line = line.strip()
        if not line:
            return False
            
        # Check for numbered steps (1., 2., Step 1, etc.)
        if re.match(r'^\d+\.?\s', line) or re.match(r'^Step\s+\d+', line, re.IGNORECASE):
            return True
            
        # Check for bullet points or dashes
        if line.startswith(('- ', '* ', '• ')):
            return True
            
        # Check for phase/section headers
        phase_patterns = [
            r'^\*\*.*Phase.*\*\*',
            r'^\*\*.*Analysis.*\*\*', 
            r'^\*\*.*Assessment.*\*\*',
            r'^\*\*.*Investigation.*\*\*',
            r'^\*\*.*Recommendations.*\*\*',
            r'^\*\*.*Summary.*\*\*'
        ]
        
        for pattern in phase_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return True
                
        return False
    
    @classmethod
    def _contains_mcp_tool(cls, line: str) -> bool:
        """Check if a line mentions MCP tool usage."""
        line_lower = line.lower()
        
        # Check for direct tool mentions
        for tool in cls.MCP_TOOLS:
            if tool.lower() in line_lower:
                return True
                
        # Check for tool call patterns
        tool_patterns = [
            r'calling.*tool',
            r'using.*tool',
            r'executing.*query',
            r'retrieving.*from.*cloudwatch',
            r'analyzing.*log.*group',
            r'fetching.*metric.*data'
        ]
        
        for pattern in tool_patterns:
            if re.search(pattern, line_lower):
                return True
                
        return False

if __name__ == "__main__":
    main()