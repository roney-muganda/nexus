TOOL_SCHEMAS = [
    {
        "name": "set_reminder",
        "description": "Creates a reminder that fires at a specific time and pushes a notification to the user's devices.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short reminder title"},
                "datetime_local": {
                    "type": "string", 
                    "description": "The exact local datetime in ISO 8601 format (e.g., '2026-06-05T15:30:00'). Calculate this based strictly on the current time provided in your system prompt. Do NOT apply any timezone conversions and NEVER output relative text like 'in 2 minutes'."
                },
                "recurrence": {"type": ["string", "null"], "description": "Optional RRULE string for repeating reminders"},
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Notification channels e.g. ['telegram', 'desktop']"
                },
                "priority": {
                    "type": "integer", 
                    "description": "Priority 1-5, 1 is highest. You MUST output a raw number (e.g., 2), NOT a string."
                }
            },
            "required": ["title", "datetime_local"]
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
    },
    {
        "name": "get_project_context",
        "description": "Retrieves the current state of a project including tasks, blockers, overdue items and recent completions. Use when the user asks about a project or wants to know what to work on next.",
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the project to look up"
                },
                "project_id": {
                    "type": "string",
                    "description": "UUID of the project if known"
                }
            },
            "required": []
        }
    },
    {
        "name": "generate_review_quiz",
        "description": "Generates a quiz from the user's stored learning notes for spaced repetition review. Use when the user wants to test themselves or review what they have studied.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["software", "civil-engineering", "general"],
                    "description": "Knowledge domain to quiz on. Omit to quiz across all domains."
                },
                "num_questions": {
                    "type": "integer",
                    "description": "Number of quiz questions to generate, default 5"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_learning_summary",
        "description": "Returns a summary of what the user has studied recently, grouped by domain. Use when asked what they have been learning or studying.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["software", "civil-engineering", "general"],
                    "description": "Filter by domain. Omit for all domains."
                },
                "days": {
                    "type": "integer",
                    "description": "How many days back to look, default 7"
                }
            },
            "required": []
        }
    },
    {
        "name": "read_emails",
        "description": "Reads and summarizes the user's Gmail inbox. Use when asked to check emails, see what's new, or get an inbox summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Number of emails to fetch, default 10"
                },
                "query": {
                    "type": "string",
                    "description": "Gmail search query e.g. 'is:unread', 'from:boss@company.com', 'subject:invoice'"
                }
            },
            "required": []
        }
    },
    {
        "name": "draft_email_reply",
        "description": "Drafts or sends an email reply. Use when the user wants to reply to an email or compose a new one.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "What the email should say — the user's intent in plain language"
                },
                "to": {
                    "type": "string",
                    "description": "Recipient email address"
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject"
                },
                "thread_id": {
                    "type": "string",
                    "description": "Gmail thread ID to reply to"
                },
                "send_immediately": {
                    "type": "boolean",
                    "description": "If true, send immediately. If false, just draft for review."
                }
            },
            "required": ["intent"]
        }
    },
    {
        "name": "create_tasks_from_email",
        "description": "Extracts action items from an email and creates tasks. Use when an email contains things to do.",
        "parameters": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "string",
                    "description": "Gmail message ID"
                }
            },
            "required": ["email_id"]
        }
    },
    {
        "name": "generate_daily_plan",
        "description": "Generates an intelligent structured plan for the user's entire day based on their tasks, learning history, preferences and energy level. Use when asked to plan the day, create a schedule, or organize the day ahead.",
        "parameters": {
            "type": "object",
            "properties": {
                "energy_level": {
                    "type": "string",
                    "enum": ["low", "normal", "high"],
                    "description": "User's energy level today"
                },
                "focus_preference": {
                    "type": "string",
                    "description": "What the user wants to focus on today e.g. 'civil engineering study' or 'NEXUS deployment'"
                },
                "custom_instructions": {
                    "type": "string",
                    "description": "Any specific adjustments to the plan"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_todays_plan",
        "description": "Retrieves the plan already generated for today. Use when asked what is on the plan, what is next, or what to do now.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]