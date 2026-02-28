"""Stateless CLI command construction helper extracted from ExecutionService.

Builds CLI commands for each supported backend (claude, opencode, gemini, codex)
with appropriate flags and argument ordering.  Pure function -- no side effects,
no I/O, no instance state.

Reference: Fowler "Refactoring" (2018) Extract Class pattern.
"""


class CommandBuilder:
    """Stateless builder for backend CLI commands."""

    @staticmethod
    def build(
        backend: str,
        prompt: str,
        allowed_paths: list = None,
        model: str = None,
        codex_settings: dict = None,
        allowed_tools: str = None,
    ) -> list:
        """Build the CLI command for the specified backend.

        Args:
            backend: Backend type ("claude", "opencode", "gemini", "codex").
            prompt: The prompt string to pass to the CLI.
            allowed_paths: Optional list of directory paths to grant access to.
            model: Optional model override (e.g. "gemini-2.0-flash", "o4-mini").
            codex_settings: Optional dict with codex-specific settings
                (e.g. {"reasoning_level": "high"}).
            allowed_tools: Optional comma-separated tool allowlist for claude backend.

        Returns:
            A list of command-line arguments suitable for subprocess.
        """
        if backend == "opencode":
            cmd = ["opencode", "run", "--format", "json", prompt]
            if model:
                cmd.extend(["--model", model])
            return cmd
        elif backend == "gemini":
            cmd = ["gemini", "-p", prompt, "--output-format", "json"]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--include-directories", path])
            return cmd
        elif backend == "codex":
            cmd = ["codex", "exec", "--json", "--full-auto"]
            if model:
                cmd.extend(["--model", model])
            if codex_settings:
                reasoning = codex_settings.get("reasoning_level")
                if reasoning and reasoning in ("low", "medium", "high"):
                    cmd.extend(["--reasoning-effort", reasoning])
            cmd.append(prompt)
            return cmd
        else:
            # claude (default)
            cmd = [
                "claude",
                "-p",
                prompt,
                "--verbose",
                "--output-format",
                "json",
                "--allowedTools",
                allowed_tools or "Read,Glob,Grep,Bash",
            ]
            if model:
                cmd.extend(["--model", model])
            if allowed_paths:
                for path in allowed_paths:
                    cmd.extend(["--add-dir", path])
            return cmd
