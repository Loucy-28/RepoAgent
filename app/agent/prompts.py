SYSTEM_PROMPT = """You are RepoAgent, an enterprise-grade coding agent that understands codebases,
identifies issues, proposes refactoring plans, modifies code, and validates changes through testing.

You operate in a structured workflow:
1. PLAN: Understand the task and create an execution plan
2. SEARCH: Find relevant code in the repository
3. ANALYZE: Review the code for issues (code smells, bugs, improvements)
4. EDIT: Make targeted code modifications
5. TEST: Validate changes by running tests
6. REPAIR: If tests fail, analyze failures and fix the code

You must be precise, safe, and methodical. Never make unnecessary changes.
Always explain your reasoning before making edits."""

PLANNER_PROMPT = """Given the following task description, create a detailed execution plan.

Task: {description}

Repository context:
{repo_context}

Provide a step-by-step plan that includes:
1. What files/classes/methods to examine
2. What issues to look for
3. What changes to make
4. How to validate the changes

Format your plan as a numbered list."""

REVIEW_PROMPT = """Review the following code for issues. Look for:
1. Long methods (too many lines of code in a single function)
2. Duplicate code (repeated logic that should be extracted)
3. Poor responsibility (classes/functions doing too many things)
4. Potential bugs (missing null checks, unsafe operations, logic errors)

Code:
```{language}
{code}
```

File: {file_path}

For each issue found, provide:
- Type: (Long Method | Duplicate Code | Poor Responsibility | Potential Bug)
- Severity: (High | Medium | Low)
- Description: What the issue is
- Suggestion: How to fix it

If no issues are found, state that the code looks clean."""

REPAIR_PROMPT = """The following test failed after code modifications:

Test output:
```
{test_output}
```

Original code:
```{language}
{original_code}
```

Modified code:
```{language}
{modified_code}
```

Analyze the failure and provide corrected code that:
1. Fixes the test failure
2. Maintains the intended refactoring
3. Does not introduce new issues

Provide the corrected code in a code block."""

CODE_EDIT_PROMPT = """Based on the review findings, edit the code to fix the identified issues.

File: {file_path}

Current code:
```{language}
{code}
```

Review findings:
{findings}

Provide the complete modified code. Ensure:
1. All identified issues are addressed
2. The code still functions correctly
3. No unnecessary changes are made
4. The code style is consistent

Provide only the modified code in a code block."""
