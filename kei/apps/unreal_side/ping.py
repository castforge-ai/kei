# kei_script: ping
# Read only. Says which engine and project answered, and echoes its input back, so Kei can check a connection.
def _main(inp):
    return {"ok": True, "engine": str(unreal.SystemLibrary.get_engine_version()),
            "project": str(unreal.SystemLibrary.get_game_name()), "echo": inp}


kei_run(_main)
