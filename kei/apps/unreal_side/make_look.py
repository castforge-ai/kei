# kei_script: make_look
# A second performer's look, in materials Kei owns: for each material slot of the mesh, a child instance of the
# slot's own material under <folder>/looks/<performer>/, with the scalar parameters the look sets. The character's
# own materials are never changed. A parameter may live in a material layer or a layer blend (as a character
# material's gameplay blends do): then it is found by its association and the layer function, as a game blueprint
# finds it, and set on that layer's index. A slot whose material lacks a parameter keeps that slot's value.
# An instance Kei made earlier for the same performer and slot is updated in place.
# Input: folder, performer, mesh, scalars [{name, value, association (global, layer or blend), layer (the layer
# function's path, for layer and blend)}]. Output: materials [path per slot], set {path: [names set]}.
ASSOCIATIONS = {"global": "GLOBAL_PARAMETER", "layer": "LAYER_PARAMETER", "blend": "BLEND_PARAMETER"}


def _names(material):
    return {str(n) for n in unreal.MaterialEditingLibrary.get_scalar_parameter_names(material)}


def _main(inp):
    folder = inp["folder"].rstrip("/") + "/looks/" + inp["performer"]
    if not folder.startswith(KEI_ROOT + "/"):
        raise RuntimeError("Kei writes only under " + KEI_ROOT + ", not " + folder)
    mesh = unreal.load_asset(inp["mesh"])
    if mesh is None:
        raise RuntimeError("the mesh " + inp["mesh"] + " is not in the project")
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    lib, assets = unreal.MaterialEditingLibrary, unreal.EditorAssetLibrary
    layers = {}
    for s in inp["scalars"]:
        if s.get("association", "global") not in ASSOCIATIONS:
            raise RuntimeError("a look parameter's association is global, layer or blend, not " + str(s["association"]))
        if s.get("association", "global") != "global":
            fn = unreal.load_asset(s.get("layer") or "")
            if fn is None:
                raise RuntimeError("the layer function " + str(s.get("layer")) + " of " + s["name"] + " is not in the project")
            layers[s["name"]] = fn
    out, done = [], {}
    for i, slot in enumerate(mesh.get_editor_property("materials")):
        parent = slot.get_editor_property("material_interface")
        if parent is None:
            out.append("")
            continue
        name = "MI_Kei_" + inp["performer"] + "_" + str(i) + "_" + parent.get_name()
        path = folder + "/" + name
        mic = assets.load_asset(path) if assets.does_asset_exist(path) else tools.create_asset(
            name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if mic is None:
            raise RuntimeError("the editor would not create " + path)
        lib.set_material_instance_parent(mic, parent)
        has = _names(parent)
        values = []
        for s in inp["scalars"]:
            if s["name"] not in has:
                continue
            assoc = getattr(unreal.MaterialParameterAssociation, ASSOCIATIONS[s.get("association", "global")])
            if s["name"] in layers:
                info = mic.get_parameter_info(assoc, s["name"], layers[s["name"]])
            else:
                info = unreal.MaterialParameterInfo(name=s["name"], association=assoc, index=-1)
            v = unreal.ScalarParameterValue()
            v.set_editor_property("parameter_info", info)
            v.set_editor_property("parameter_value", float(s["value"]))
            values.append(v)
        mic.set_editor_property("scalar_parameter_values", values)
        lib.update_material_instance(mic)
        if not assets.save_asset(path, only_if_is_dirty=False):
            raise RuntimeError("the editor would not save " + path)
        out.append(path)
        done[path] = [str(v.parameter_info.name) for v in values]
    return {"materials": out, "set": done, "dirty": dirty_packages()}


kei_run(_main)
