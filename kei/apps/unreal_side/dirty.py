# kei_script: dirty
# Read only. The names of every dirty content package and dirty map package in the editor.
def _main(inp):
    return {"dirty": dirty_packages()}


kei_run(_main)
