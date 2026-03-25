# Removing A Public Directory From Git History

Use this when a directory should never have been committed to the public repo and
must be removed from branch history, not just deleted from the latest commit.

## Why `git rm` is not enough

`git rm prod/Q3` only removes the directory from the current tip commit. The
content still exists in older commits, old branches, old clones, and GitHub
archives.

To remove it properly, rewrite every affected branch with `git filter-repo`, then
force-push those rewritten branches.

## Singine planner

Start with a dry run:

```bash
singine git rm-public-dir github/singine prod/Q3 \
  -all
```

Development machine prerequisite:

```bash
make install-workstation
# or
singine install --mode workstation
```

That workstation install profile ensures `git-filter-repo` is present. If you
need only that one dependency:

```bash
singine install git-filter-repo
```

That command does not push anything. It prints:

- the normalized directory path that will be removed
- the set of local branches whose history contains that path
- the exact `git filter-repo` command
- the exact force-push commands for each branch
- warnings if the local clone or branch list does not match what you asked for
- a reminder that `-all` only scans local heads, so you should fetch missing branches first

JSON form:

```bash
singine git rm-public-dir github/singine prod/Q3 \
  -all \
  --json
```

If you already know the exact branches, you can still specify them manually with
repeated `--branch` flags. You can also combine manual branches with `-all`; the
rewrite set is the union of both.

## Exact workflow

1. Work in a dedicated rewrite clone, not in your everyday checkout.
2. Fetch every branch that ever carried the unwanted directory.
3. Run `singine git rm-public-dir ... -all` to discover the relevant local heads.
4. Rewrite those branches with `git filter-repo`.
5. Force-push the rewritten branches.
6. Tell collaborators to reclone or hard-reset so the old history does not come back.

Concrete commands:

```bash
git fetch origin --prune
singine git rm-public-dir github/singine prod/Q3 -all
git filter-repo --path prod/Q3/ --invert-paths --refs refs/heads/main refs/heads/release/2026Q3
git for-each-ref --format='delete %(refname)' refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now
git push --force-with-lease origin refs/heads/main:refs/heads/main
git push --force-with-lease origin refs/heads/release/2026Q3:refs/heads/release/2026Q3
```

## Optional local execution

If you are already inside the dedicated rewrite clone and want Singine to run the
local rewrite command for you:

```bash
singine git rm-public-dir github/singine prod/Q3 \
  -all \
  --execute
```

`--execute` runs the local `git-filter-repo` rewrite only. It does not push. The
force-push step stays explicit on purpose.

## After the rewrite

- Recheck with `git log -- prod/Q3/`.
- Recheck each target branch on GitHub after the force-push.
- If the directory contained secrets, rotate them. History rewrite does not make old copies disappear from forks or local clones you do not control.
