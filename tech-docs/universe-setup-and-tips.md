# Universe Setup and Tips

## Universe Repo Setup on Local

You have the option to use Arca for development, but for agent skills work most of the team prefers to work from their local environment. The following are key commands to do the initial configuration and some common commands.

### Initial Setup on Local

```bash
git clone --depth 10 git@github.com:databricks-eng/universe.git
cd universe
git remote rename origin databricks
git remote add origin git@github.com:databricks-eng/universe-dev.git
git config feature.manyFiles true

export github_username=<Your EMU username: first-last_data>
git config remote.origin.fetch "+refs/heads/${github_username}/*:refs/remotes/origin/${github_username}/*"
git config remote.origin.tagOpt --no-tags
```

### Common commands

1. Fetch master quickly:

   ```bash
   git fetch --depth=6 databricks master
   ```

2. Push and create PR:

   ```bash
   git pp
   ```

## Isaac-bot and special commands

A lot can be done via Isaac-bot once you create a PR. Here are a few of our favorite commands.

1. Rebase on master is a long-running command, so it's easier to do from the PR:

   ```text
   isaac-bot rebase on latest master
   ```

2. Fix linting:

   ```text
   isaac-bot fix linting (prettier)
   ```

3. When approved and ready to merge:

   ```text
   /merge
   ```

4. To automatically merge when all CI is done, add the `automerge` label.

5. For work related to Genie Code skills or agents, trigger evals:

   ```text
   /trigger EvalRunner-Pr
   ```

6. Add the `autoformat` tag to the PR to try to keep it formatted correctly. This may not be relevant for agent skills.
