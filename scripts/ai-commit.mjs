#!/usr/bin/env node

/**
 * AI-powered commit message generator using Claude CLI.
 *
 * Usage:
 *   node scripts/ai-commit.mjs            # Commit staged changes (must git add first)
 *   node scripts/ai-commit.mjs --all      # Auto-stage all modified files then commit
 *   node scripts/ai-commit.mjs --dry-run  # Preview message without committing
 *   node scripts/ai-commit.mjs --amend    # Amend last commit with new message
 *   node scripts/ai-commit.mjs --push     # Auto-push after commit
 *
 * Requirements:
 *   - Claude CLI installed and available in PATH
 */

import { execSync } from "child_process";
import fs from "fs";
import os from "os";
import path from "path";
import readline from "readline";

const args = process.argv.slice(2);
const isDryRun = args.includes("--dry-run");
const isAmend = args.includes("--amend");
const isAll = args.includes("--all");
const isPush = args.includes("--push");
const noConfirm = args.includes("--no-confirm");

if (args.includes("--help") || args.includes("-h")) {
  console.log(`Usage: node scripts/ai-commit.mjs [OPTIONS]

Options:
  --all         Stage all modified/deleted files before committing
  --amend       Amend the last commit instead of creating new
  --push        Auto-push to remote after commit
  --no-confirm  Skip confirmation prompt
  --dry-run     Generate message but don't commit
  -h, --help    Show this help`);
  process.exit(0);
}

// --- Helpers ---

function run(cmd, opts = {}) {
  try {
    return execSync(cmd, { encoding: "utf-8", maxBuffer: 2 * 1024 * 1024, ...opts }).trim();
  } catch (e) {
    return e.stdout?.trim() || "";
  }
}

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer.trim().toLowerCase());
    });
  });
}

function cleanMessage(msg) {
  return msg
    .replace(/^```[\w]*\n?/, "")
    .replace(/\n?```$/, "")
    .replace(/^["']|["']$/g, "")
    .trim();
}

function generateMessage(diff, stagedFiles, recentCommits) {
  const prompt = `Generate a git commit message for the following changes.

## Rules (STRICT)
- Format: \`<type>(<scope>): <subject>\`
- Types: feat, fix, refactor, perf, style, docs, test, chore, ci, revert
- English, present tense, imperative mood, no capital start, no trailing dot, max 72 chars for subject
- Scope is optional. Use it only when changes are focused on a single area.
- Add a blank line then a body (2-5 bullet points) for non-trivial changes.
- One commit = one purpose. Use \`refactor\` only when behavior does not change.
- Do NOT include Co-Authored-By or any footer.

## Recent commits (follow this style)
${recentCommits}

## Staged files
${stagedFiles}

## Diff
${diff.slice(0, 8000)}

Respond ONLY with the commit message. No explanation, no markdown fences, no quotes.`;

  // Write prompt to temp file to avoid shell escaping issues
  const promptFile = path.join(os.tmpdir(), `claude-commit-${Date.now()}.txt`);
  fs.writeFileSync(promptFile, prompt);

  try {
    const msg = run(`claude -p < "${promptFile}"`, { timeout: 60000 });
    return cleanMessage(msg);
  } finally {
    try { fs.unlinkSync(promptFile); } catch { /* ignore */ }
  }
}

// --- Main ---

async function main() {
  // 1. Preflight checks
  if (!run("git rev-parse --is-inside-work-tree")) {
    console.error("Error: not a git repository");
    process.exit(1);
  }

  // 2. Auto-stage if --all
  if (isAll) {
    const unstaged = run("git diff --name-only");
    const untracked = run("git ls-files --others --exclude-standard");
    if (unstaged || untracked) {
      console.log("Staging all changes...\n");
      run("git add -A");
    }
  }

  // 3. Check for staged changes
  const stagedFiles = run("git diff --cached --name-only");

  if (!stagedFiles && !isAmend) {
    // Nothing staged — prompt to stage
    const status = run("git status --short");
    if (!status) {
      console.log("No changes to commit.");
      process.exit(0);
    }

    console.log("No staged changes found.\n");
    console.log("Unstaged changes:");
    console.log(status);
    console.log();

    const answer = await ask("Stage all changes? [Y/n] ");
    if (answer === "n") {
      console.log("Aborted. Stage files manually with 'git add' first.");
      process.exit(0);
    }
    run("git add -A");
    console.log();
  }

  // 4. Collect context
  const diff = run("git diff --cached");
  const files = run("git diff --cached --name-only");
  const stat = run("git diff --cached --stat");
  const recentCommits = run("git log --oneline -10") || "No previous commits";

  if (!diff && !isAmend) {
    console.error("No diff found in staged changes.");
    process.exit(1);
  }

  console.log("Generating commit message with Claude...\n");

  // 5. Generate message
  let commitMessage = generateMessage(diff, files, recentCommits);

  if (!commitMessage) {
    console.error("Failed to generate commit message.");
    process.exit(1);
  }

  // 6. Display
  console.log("Generated commit message:\n");
  console.log("\x1b[36m" + "─".repeat(60) + "\x1b[0m");
  console.log(commitMessage);
  console.log("\x1b[36m" + "─".repeat(60) + "\x1b[0m");

  if (isDryRun) {
    console.log("\nDry run — no commit created.");
    return;
  }

  // 7. Confirm
  if (!noConfirm) {
    console.log("\n  c = commit   e = edit   r = regenerate   q = quit");
    const action = await ask("Action [c/e/r/q]: ") || "c";

    if (action === "q" || action === "n") {
      console.log("Aborted.");
      process.exit(0);
    }

    if (action === "e") {
      const tmpFile = path.join(os.tmpdir(), "COMMIT_EDITMSG");
      fs.writeFileSync(tmpFile, commitMessage);
      const editor = process.env.EDITOR || process.env.VISUAL || "notepad";
      execSync(`${editor} "${tmpFile}"`, { stdio: "inherit" });
      commitMessage = fs.readFileSync(tmpFile, "utf-8").trim();
      try { fs.unlinkSync(tmpFile); } catch { /* ignore */ }
    }

    if (action === "r") {
      console.log("\nRegenerating...\n");
      commitMessage = generateMessage(diff, files, recentCommits);

      if (!commitMessage) {
        console.error("Failed to regenerate.");
        process.exit(1);
      }

      console.log("New commit message:\n");
      console.log("\x1b[36m" + "─".repeat(60) + "\x1b[0m");
      console.log(commitMessage);
      console.log("\x1b[36m" + "─".repeat(60) + "\x1b[0m");

      const confirm = await ask("\nCommit this? [Y/n] ") || "y";
      if (confirm === "n") {
        console.log("Aborted.");
        process.exit(0);
      }
    }
  }

  // 8. Commit using temp file (avoids shell escaping issues with message)
  const msgFile = path.join(os.tmpdir(), `git-commit-msg-${Date.now()}.txt`);
  fs.writeFileSync(msgFile, commitMessage);

  try {
    const amendFlag = isAmend ? "--amend" : "";
    const result = run(`git commit ${amendFlag} -F "${msgFile}"`);
    console.log(`\n\x1b[32mCommitted!\x1b[0m\n${result}`);
  } catch (e) {
    console.error("Commit failed:", e.message);
    process.exit(1);
  } finally {
    try { fs.unlinkSync(msgFile); } catch { /* ignore */ }
  }

  // 9. Push if requested
  if (isPush) {
    const branch = run("git branch --show-current");
    console.log(`\nPushing to origin/${branch}...`);
    run(`git push origin ${branch}`);
    console.log("\x1b[32mPushed.\x1b[0m");
  }
}

main().catch((e) => {
  console.error(e.message);
  process.exit(1);
});
