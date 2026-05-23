# Ship Changes as PR

Create a branch from dev, commit all pending changes, push, and open a PR targeting dev.

## Steps

1. **Check current state** — run `git fetch origin` to get the latest remote state, then run `git status` and `git diff` to understand what's changed. Also check the current branch with `git branch --show-current`. If we're on `dev`, ensure the local branch is up to date with `git pull origin dev` before branching.

2. **Ensure we're working from dev** — if there are uncommitted changes on a non-dev branch already, proceed on the current branch. If we're on `dev` with uncommitted changes, create a new branch before committing.

3. **Generate a branch name** — look at the staged and unstaged diffs to infer what the changes are about. Produce a short kebab-case branch name that describes the work (e.g., `fix-auth-redirect`, `add-area-filter`, `update-scraper`). Do not use generic names like `changes` or `update`. The branch name must not already exist remotely — check with `git branch -r`.

4. **Create and checkout the branch** — if needed, run `git checkout -b <branch-name>` from the current HEAD.

5. **Stage all changes** — run `git add -A` unless the user specified particular files.

6. **Run ruff** — run `docker compose exec web ruff check . --fix` and `docker compose exec web ruff format .` from the project root to auto-fix and format. If either modifies files, re-stage with `git add -A`. If Docker is not running, skip this step and note it in the response.

7. **Commit** — write a concise commit message that summarises the work (imperative mood, present tense, under 72 chars). Use a heredoc to pass the message:
   ```
   git commit -m "$(cat <<'EOF'
   <message>
   EOF
   )"
   ```

8. **Push** — run `git push -u origin <branch-name>`.

9. **Create the PR** — use the `mcp__github__create_pull_request` tool with:
   - `owner` and `repo` derived from `git remote get-url origin`
   - `head`: the new branch name
   - `base`: `dev`
   - `title`: always `"Merge <branch-name> into dev"` (e.g., `"Merge fix-auth-redirect into dev"`)
   - `body`: omit (leave empty — commit messages carry all the context)

10. **Report** — print the PR URL so the user can see it.

## Notes

- If there are no uncommitted changes at all, tell the user and stop.
- If the current branch is already a feature branch (not dev) with no remote tracking branch, skip step 4 and just push it.
- If a pre-commit hook fails, fix the issue and retry rather than skipping the hook.
- Never force-push.
- Always confirm the PR was created successfully and share the URL.
