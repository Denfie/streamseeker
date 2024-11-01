![Streamseeker usage](https://raw.githubusercontent.com/uniprank/streamseeker/master/assets/usage-v-0-1-2.gif)

### poetry issues

`python -m venv .venv --copies` creates a virtual environment with copies of the system packages. Poetry does not support this feature. If you encounter an error like `ERROR: Error: Command '['/home/runner/work/streamseeker/streamseeker/.venv/bin/python3', '-Im', 'ensurepip', '--upgrade', '--default-pip']' returned non-zero exit status 1.` you can create a virtual environment without copies by running `python -m venv .venv` instead.

```bash
# Enter the current Poetry environment
poetry shell

# Remove the current environment
# as referred by path to Python interpreter
poetry env remove $(which python)

# Reinstall from Poetry's cache
poetry install
```
