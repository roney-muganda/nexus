TOOL_SCHEMAS = [
    {
        "name": "set_reminder",
        "description": "Creates a reminder that fires at a specific time and pushes a notification to the user's devices.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short reminder title"},
                "datetime_utc": {"type": "string", "description": "ISO 8601 datetime in UTC e.g. 2024-01-15T09:00:00Z"},
                "recurrence": {"type": "string", "description": "Optional RRULE string for repeating reminders"},
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notification channels e.g. ['telegram', 'desktop']"
                },
                "priority": {"type": "integer", "description": "Priority 1-5, 1 is highest"}
            },
            "required": ["title", "datetime_utc"]
        }
    },
    {
        "name": "search_technical_docs",
        "description": "Searches indexed technical documentation and returns relevant chunks. Use for programming questions, library usage, and technical references.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by source tags e.g. ['python', 'civil-engineering']"
                },
                "top_k": {"type": "integer", "description": "Number of results to return, default 5"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "execute_terminal_command",
        "description": "Executes a shell command on the user's Windows laptop via the Desktop spoke. Use for file operations, git commands, running scripts.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "working_dir": {"type": "string", "description": "Working directory path"},
                "timeout_s": {"type": "integer", "description": "Timeout in seconds, default 30"},
                "require_confirm": {"type": "boolean", "description": "If true, ask user to confirm before running"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "update_project_milestone",
        "description": "Creates or updates a project task or milestone. Use when the user mentions project progress, deadlines, or task status.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task or milestone title"},
                "status": {
                    "type": "string",
                    "enum": ["todo", "in_progress", "done", "blocked"],
                    "description": "Current status"
                },
                "priority": {"type": "integer", "description": "Priority 1-5"},
                "due_date": {"type": "string", "description": "ISO 8601 date e.g. 2024-01-15"},
                "notes": {"type": "string", "description": "Additional context or notes"}
            },
            "required": ["title", "status"]
        }
    },
    {
        "name": "store_memory",
        "description": "Stores an important piece of information in long-term memory for future recall. Use when the user shares preferences, facts about themselves, or important context.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The information to remember"},
                "memory_type": {
                    "type": "string",
                    "enum": ["fact", "preference", "skill", "event", "relationship", "learning"],
                    "description": "Category of the memory"
                },
                
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for filtering e.g. ['civil-engineering', 'personal']"
                }
            },
            "required": ["content", "memory_type"]
        }
    },
    {
        "name": "store_learning",
        "description": "Stores something the user learned for spaced repetition review later. Use when user is studying or learning new concepts.",
        "parameters": {
            "type": "object",
            "properties": {
                "concept": {"type": "string", "description": "The concept or topic learned"},
                "explanation": {"type": "string", "description": "Explanation or notes about the concept"},
                "domain": {
                    "type": "string",
                    "enum": ["software", "civil-engineering", "general"],
                    "description": "Knowledge domain"
                },
                "source": {"type": "string", "description": "Where this was learned from"}
            },
            "required": ["concept", "explanation", "domain"]
        }
    },
    {
        "name": "web_search_and_summarize",
        "description": "Searches the web for current information and returns a summary. Use for recent events, documentation not in the knowledge base, or anything requiring up-to-date information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_sources": {"type": "integer", "description": "Number of sources to check, default 3"},
                "store_in_memory": {"type": "boolean", "description": "Whether to save the summary to memory"}
            },
            "required": ["query"]
        }
    }
]