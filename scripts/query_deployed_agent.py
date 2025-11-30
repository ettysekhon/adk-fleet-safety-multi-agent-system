#!/usr/bin/env python3
"""
CLI script to query the deployed Fleet Safety Agent on Vertex AI Agent Engine.

Usage:
    # Interactive mode
    python scripts/query_deployed_agent.py

    # Single query
    python scripts/query_deployed_agent.py --query "What is the fleet status?"

    # With custom user ID
    python scripts/query_deployed_agent.py --user demo_user --query "Plan a route from London to Manchester"
"""

import argparse
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vertexai
from vertexai import agent_engines


# Configuration - update these if needed
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "simple-gcp-data-pipeline")
LOCATION = os.environ.get("GOOGLE_CLOUD_REGION", "europe-west2")
AGENT_ENGINE_ID = "8524575222798483456"


def get_agent():
    """Initialise and return the deployed agent."""
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    return agent_engines.get(AGENT_ENGINE_ID)


def create_session(agent, user_id: str) -> str:
    """Create a new session and return the session ID."""
    session = agent.create_session(user_id=user_id)
    return session["id"]


def query_agent(agent, user_id: str, session_id: str, message: str) -> str:
    """Send a query to the agent and return the response."""
    response_text = ""
    
    print("\nAgent Response:\n")
    print("-" * 60)
    
    for chunk in agent.stream_query(
        user_id=user_id,
        session_id=session_id,
        message=message
    ):
        # Agent Engine returns dict chunks with 'content' containing 'parts'
        if isinstance(chunk, dict):
            content = chunk.get('content', {})
            if isinstance(content, dict):
                parts = content.get('parts', [])
                for part in parts:
                    if isinstance(part, dict) and 'text' in part:
                        text = part['text']
                        print(text, end="", flush=True)
                        response_text += text
        elif isinstance(chunk, str):
            print(chunk, end="", flush=True)
            response_text += chunk
        elif hasattr(chunk, 'content'):
            # Handle object-style responses
            content = chunk.content
            if hasattr(content, 'parts'):
                for part in content.parts:
                    if hasattr(part, 'text') and part.text:
                        print(part.text, end="", flush=True)
                        response_text += part.text
    
    print("\n" + "-" * 60)
    return response_text


def interactive_mode(agent, user_id: str):
    """Run in interactive mode with continuous conversation."""
    print(f"""
Fleet Safety Agent - Interactive Mode
=====================================

Project:  {PROJECT_ID}
Region:   {LOCATION}
Agent ID: {AGENT_ENGINE_ID}
User:     {user_id}

Commands:
  'quit' or 'exit' - End the session
  'new'            - Start a new session
""")
    
    session_id = create_session(agent, user_id)
    print(f"Session created: {session_id[:20]}...\n")
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nSession ended.")
                break
            
            if user_input.lower() == 'new':
                session_id = create_session(agent, user_id)
                print(f"New session created: {session_id[:20]}...")
                continue
            
            query_agent(agent, user_id, session_id, user_input)
            
        except KeyboardInterrupt:
            print("\n\nSession ended.")
            break
        except Exception as e:
            print(f"\nError: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Query the deployed Fleet Safety Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python scripts/query_deployed_agent.py

  # Single query
  python scripts/query_deployed_agent.py -q "What is the fleet status?"

  # Route planning query
  python scripts/query_deployed_agent.py -q "Plan a safe route from London to Manchester for vehicle v001"
        """
    )
    parser.add_argument(
        "-q", "--query",
        help="Single query to send (omit for interactive mode)"
    )
    parser.add_argument(
        "-u", "--user",
        default="cli_user",
        help="User ID for the session (default: cli_user)"
    )
    parser.add_argument(
        "--project",
        default=PROJECT_ID,
        help=f"GCP Project ID (default: {PROJECT_ID})"
    )
    parser.add_argument(
        "--location",
        default=LOCATION,
        help=f"GCP Location (default: {LOCATION})"
    )
    parser.add_argument(
        "--agent-id",
        default=AGENT_ENGINE_ID,
        help=f"Agent Engine ID (default: {AGENT_ENGINE_ID})"
    )
    
    args = parser.parse_args()
    
    # Use args values (they default to the module-level constants)
    project_id = args.project
    location = args.location
    agent_id = args.agent_id
    
    print("Connecting to deployed agent...")
    vertexai.init(project=project_id, location=location)
    agent = agent_engines.get(agent_id)
    print("Connected.\n")
    
    if args.query:
        # Single query mode
        session_id = create_session(agent, args.user)
        query_agent(agent, args.user, session_id, args.query)
    else:
        # Interactive mode
        interactive_mode(agent, args.user)


if __name__ == "__main__":
    main()
