from typing import Optional, NamedTuple
import bpy


from ..cwxml.shader import (
    ShaderManager,
    ShaderDef,
    ShaderParameterType,
    ShaderParameterSubtype,
    ShaderParameterFloatDef,
    ShaderParameterFloat2Def,
    ShaderParameterFloat3Def,
    ShaderParameterFloat4Def,
    ShaderParameterFloat4x4Def,
)
from ..sollumz_properties import MaterialType, MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID
from ..tools.animationhelper import add_global_anim_uv_nodes
from ..tools.blenderhelper import find_bsdf_and_material_output
from ..tools.meshhelper import get_uv_map_name, get_color_attr_name
from ..shared.shader_nodes import SzShaderNodeParameter, SzShaderNodeParameterDisplayType
from ..shared.shader_expr import expr, compile_expr
from .render_bucket import RenderBucket


class ShaderBuilder(NamedTuple):
    shader: ShaderDef
    filename: str
    material: bpy.types.Material
    node_tree: bpy.types.ShaderNodeTree
    bsdf: bpy.types.ShaderNodeBsdfPrincipled
    material_output: bpy.types.ShaderNodeOutputMaterial


class ShaderMaterial(NamedTuple):
    name: str
    ui_name: str
    value: str


shadermats = []

for shader in ShaderManager._shaders.values():
    name = shader.filename.replace(".sps", "").upper()

    shadermats.append(ShaderMaterial(name, name.replace("_", " "), shader.filename))

shadermats_by_filename = {s.value: s for s in shadermats}


def try_get_node(node_tree: bpy.types.NodeTree, name: str) -> Optional[bpy.types.Node]:
    """Gets a node by its name. Returns `None` if not found.
    Note, names are localized by Blender or can changed by the user, so
    this should only be used for names that Sollumz sets explicitly.
    """
    return node_tree.nodes.get(name, None)


def try_get_node_by_cls(node_tree: bpy.types.NodeTree, node_cls: type) -> Optional[bpy.types.Node]:
    """Gets a node by its type. Returns `None` if not found."""
    for node in node_tree.nodes:
        if isinstance(node, node_cls):
            return node

    return None


def get_child_nodes(node):
    child_nodes = []
    for input in node.inputs:
        for link in input.links:
            child = link.from_node
            if child in child_nodes:
                continue
            else:
                child_nodes.append(child)
    return child_nodes


def group_image_texture_nodes(node_tree):
    image_texture_nodes = [node for node in node_tree.nodes if node.type == "TEX_IMAGE"]

    if not image_texture_nodes:
        return

    image_texture_nodes.sort(key=lambda node: node.location.y)

    avg_x = min([node.location.x for node in image_texture_nodes])

    # adjust margin to change gap in between img nodes
    margin = 275
    current_y = min([node.location.y for node in image_texture_nodes]) - margin
    for node in image_texture_nodes:
        current_y += margin
        node.location.x = avg_x
        node.location.y = current_y

    # how far to the left the img nodes are
    group_offset = 400
    for node in image_texture_nodes:
        node.location.x -= group_offset
        node.location.y += group_offset


def group_uv_map_nodes(node_tree):
    uv_map_nodes = [node for node in node_tree.nodes if node.type == "UVMAP"]

    if not uv_map_nodes:
        return

    uv_map_nodes.sort(key=lambda node: node.name, reverse=True)

    avg_x = min([node.location.x for node in uv_map_nodes])

    # adjust margin to change gap in between UV map nodes
    margin = 120
    current_y = min([node.location.y for node in uv_map_nodes]) - margin
    for node in uv_map_nodes:
        current_y += margin
        node.location.x = avg_x
        node.location.y = current_y

    # how far to the left the UV map nodes are
    group_offset = 900
    for node in uv_map_nodes:
        node.location.x -= group_offset
        node.location.y += group_offset


def get_loose_nodes(node_tree):
    loose_nodes = []
    for node in node_tree.nodes:
        no = False
        ni = False
        for output in node.outputs:
            for link in output.links:
                if link.to_node is not None and link.from_node is not None:
                    no = True
                    break
        for input in node.inputs:
            for link in input.links:
                if link.to_node is not None and link.from_node is not None:
                    ni = True
                    break
        if no == False and ni == False:
            loose_nodes.append(node)
    return loose_nodes


def organize_node_tree(b: ShaderBuilder):
    mo = b.material_output
    mo.location.x = 0
    mo.location.y = 0
    organize_node(mo)
    organize_loose_nodes(b.node_tree, 1000, 0)
    group_image_texture_nodes(b.node_tree)
    group_uv_map_nodes(b.node_tree)


def organize_node(node):
    child_nodes = get_child_nodes(node)
    if len(child_nodes) < 0:
        return

    level = node.location.y
    for child in child_nodes:
        child.location.x = node.location.x - 300
        child.location.y = level
        level -= 300
        organize_node(child)


def organize_loose_nodes(node_tree, start_x, start_y):
    loose_nodes = get_loose_nodes(node_tree)
    if len(loose_nodes) == 0:
        return

    grid_x = start_x
    grid_y = start_y

    for i, node in enumerate(loose_nodes):
        if i % 4 == 0:
            grid_x = start_x
            grid_y -= 150

        node.location.x = grid_x + node.width / 2
        node.location.y = grid_y - node.height / 2

        grid_x += node.width + 25


def get_tint_sampler_node(mat: bpy.types.Material) -> Optional[bpy.types.ShaderNodeTexImage]:
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.name == "TintPaletteSampler" and isinstance(node, bpy.types.ShaderNodeTexImage):
            return node

    return None


def get_detail_extra_sampler(mat):  # move to blenderhelper.py?
    nodes = mat.node_tree.nodes
    for node in nodes:
        if node.name == "Extra":
            return node
    return None


def create_tinted_shader_graph(obj: bpy.types.Object):
    attribute_to_remove = []
    modifiers_to_remove = []

    for mod in obj.modifiers:
        if mod.type == "NODES":
            for mat in obj.data.materials:
                tint_node = get_tint_sampler_node(mat)
                if tint_node is not None:
                    output_id = mod.node_group.interface.items_tree.get("Tint Color")
                    if output_id:
                        attr_name = mod[output_id.identifier + "_attribute_name"]
                        if attr_name and attr_name in obj.data.attributes:
                            attribute_to_remove.append(attr_name)

                    modifiers_to_remove.append(mod)
                    break

    for attr_name in attribute_to_remove:
        obj.data.attributes.remove(obj.data.attributes[attr_name])

    for mod in modifiers_to_remove:
        obj.modifiers.remove(mod)

    tint_mats = get_tinted_mats(obj)

    if not tint_mats:
        return

    for mat in tint_mats:
        tint_sampler_node = get_tint_sampler_node(mat)
        palette_img = tint_sampler_node.image

        if tint_sampler_node is None:
            continue

        if mat.shader_properties.filename in ShaderManager.tint_colour1_shaders:
            input_color_attr_name = get_color_attr_name(1)
        else:
            input_color_attr_name = get_color_attr_name(0)

        tint_color_attr_name = f"TintColor ({palette_img.name})" if palette_img else "TintColor"
        # Attribute creation fails with names that are too long. Truncate to max name length 64 characters, -4 so
        # Blender still has space to append '.012' in case of duplicated names.
        tint_color_attr_name = tint_color_attr_name[:64-4]

        tint_color_attr = obj.data.attributes.new(name=tint_color_attr_name, type="BYTE_COLOR", domain="CORNER")

        rename_tint_attr_node(mat.node_tree, name=tint_color_attr.name)

        create_tint_geom_modifier(obj, tint_color_attr.name, input_color_attr_name, palette_img)


def create_tint_geom_modifier(
    obj: bpy.types.Object,
    tint_color_attr_name: str,
    input_color_attr_name: Optional[str],
    palette_img: Optional[bpy.types.Image]
) -> bpy.types.NodesModifier:
    tnt_ng = create_tinted_geometry_graph()
    mod = obj.modifiers.new("GeometryNodes", "NODES")
    mod.node_group = tnt_ng

    # set input / output variables
    input_id = tnt_ng.interface.items_tree["Color Attribute"].identifier
    mod[input_id + "_attribute_name"] = input_color_attr_name if input_color_attr_name is not None else ""
    mod[input_id + "_use_attribute"] = True

    input_palette_id = tnt_ng.interface.items_tree["Palette Texture"].identifier
    mod[input_palette_id] = palette_img

    output_id = tnt_ng.interface.items_tree["Tint Color"].identifier
    mod[output_id + "_attribute_name"] = tint_color_attr_name
    mod[output_id + "_use_attribute"] = True

    return mod


def rename_tint_attr_node(node_tree: bpy.types.NodeTree, name: str):
    assert name.startswith("TintColor"), "Tint attributes should always be prefixed with 'TintColor'"
    for node in node_tree.nodes:
        if not isinstance(node, bpy.types.ShaderNodeAttribute) or not node.attribute_name.startswith("TintColor"):
            continue

        node.attribute_name = name
        return


def get_tinted_mats(obj: bpy.types.Object) -> list[bpy.types.Material]:
    if obj.data is None or not obj.data.materials:
        return []

    return [mat for mat in obj.data.materials if is_tint_material(mat)]


def obj_has_tint_mats(obj: bpy.types.Object) -> bool:
    if not obj.data.materials:
        return False

    mat = obj.data.materials[0]
    return is_tint_material(mat)


def is_tint_material(mat: bpy.types.Material) -> bool:
    return get_tint_sampler_node(mat) is not None


def link_geos(links, node1, node2):
    links.new(node1.inputs["Geometry"], node2.outputs["Geometry"])


def create_tinted_geometry_graph():  # move to blenderhelper.py?
    gnt = bpy.data.node_groups.new(name="TintGeometry", type="GeometryNodeTree")
    input = gnt.nodes.new("NodeGroupInput")
    output = gnt.nodes.new("NodeGroupOutput")

    # Create the necessary sockets for the node group
    gnt.interface.new_socket("Geometry", socket_type="NodeSocketGeometry", in_out="INPUT")
    gnt.interface.new_socket("Geometry", socket_type="NodeSocketGeometry", in_out="OUTPUT")
    gnt.interface.new_socket("Color Attribute", socket_type="NodeSocketVector", in_out="INPUT")
    in_palette = gnt.interface.new_socket("Palette (Preview)",
                                          description="Index of the tint palette to preview. Has no effect on export",
                                          socket_type="NodeSocketInt", in_out="INPUT")
    in_palette.min_value = 0
    gnt.interface.new_socket("Palette Texture", description="Should be the same as 'TintPaletteSampler' of the material",
                             socket_type="NodeSocketImage", in_out="INPUT")
    gnt.interface.new_socket("Tint Color", socket_type="NodeSocketColor", in_out="OUTPUT")

    # link input / output node to create geometry socket
    cptn = gnt.nodes.new("GeometryNodeCaptureAttribute")
    cptn.domain = "CORNER"
    if bpy.app.version >= (4, 2, 0):
        cpt_name = "UV"
        cpt_attr = cptn.capture_items.new("VECTOR", cpt_name)
        cpt_attr.data_type = "FLOAT_VECTOR"
    else:
        cpt_name = "Attribute"
        cptn.data_type = "FLOAT_VECTOR"
    gnt.links.new(input.outputs["Geometry"], cptn.inputs["Geometry"])
    gnt.links.new(cptn.outputs["Geometry"], output.inputs["Geometry"])

    # create and link texture node
    txtn = gnt.nodes.new("GeometryNodeImageTexture")
    txtn.interpolation = "Closest"
    gnt.links.new(input.outputs["Palette Texture"], txtn.inputs["Image"])
    gnt.links.new(cptn.outputs[cpt_name], txtn.inputs["Vector"])
    gnt.links.new(txtn.outputs["Color"], output.inputs["Tint Color"])

    pal_img_info = gnt.nodes.new("GeometryNodeImageInfo")
    gnt.links.new(input.outputs["Palette Texture"], pal_img_info.inputs["Image"])

    # separate colour0
    sepn = gnt.nodes.new("ShaderNodeSeparateXYZ")
    gnt.links.new(input.outputs["Color Attribute"], sepn.inputs["Vector"])

    # create math nodes
    mathns = []
    for i in range(9):
        mathns.append(gnt.nodes.new("ShaderNodeMath"))

    # Convert color attribute from linear to sRGB
    # Sollumz imports it as sRGB but accessing in the node tree gives you linear color
    # c1
    mathns[0].operation = "LESS_THAN"
    gnt.links.new(sepn.outputs[2], mathns[0].inputs[0])
    # NOTE: the correct constant here should be 0.0031308 but the loss of precision due to the linear->sRGB conversion
    #       causes it not to recover the correct UV.x value on some pixels, sampling neighboring pixels. With 0.004, it
    #       works better in our specific case (UVs for pixels between 0-256) and seems to work for all palette pixels.
    mathns[0].inputs[1].default_value = 0.004
    mathns[1].operation = "SUBTRACT"
    gnt.links.new(mathns[0].outputs[0], mathns[1].inputs[1])
    mathns[1].inputs[0].default_value = 1.0

    # r1
    mathns[2].operation = "MULTIPLY"
    gnt.links.new(sepn.outputs[2], mathns[2].inputs[0])
    mathns[2].inputs[1].default_value = 12.920
    mathns[3].operation = "MULTIPLY"
    gnt.links.new(mathns[2].outputs[0], mathns[3].inputs[0])
    gnt.links.new(mathns[0].outputs[0], mathns[3].inputs[1])

    # r2
    mathns[4].operation = "POWER"
    gnt.links.new(sepn.outputs[2], mathns[4].inputs[0])
    mathns[4].inputs[1].default_value = 0.417
    mathns[5].operation = "MULTIPLY"
    gnt.links.new(mathns[4].outputs[0], mathns[5].inputs[0])
    mathns[5].inputs[1].default_value = 1.055
    mathns[6].operation = "SUBTRACT"
    gnt.links.new(mathns[5].outputs[0], mathns[6].inputs[0])
    mathns[6].inputs[1].default_value = 0.055
    mathns[7].operation = "MULTIPLY"
    gnt.links.new(mathns[6].outputs[0], mathns[7].inputs[0])
    gnt.links.new(mathns[1].outputs[0], mathns[7].inputs[1])

    # add r1 and r2
    mathns[8].operation = "ADD"
    gnt.links.new(mathns[3].outputs[0], mathns[8].inputs[0])
    gnt.links.new(mathns[7].outputs[0], mathns[8].inputs[1])

    # Select palette row
    # uv.y = (palette_preview_index + 0.5) / img.height
    # uv.y = ((uv.y - 1) * -1)   ; flip_uv
    pal_add = gnt.nodes.new("ShaderNodeMath")
    pal_add.operation = "ADD"
    pal_add.inputs[1].default_value = 0.5
    pal_div = gnt.nodes.new("ShaderNodeMath")
    pal_div.operation = "DIVIDE"
    pal_flip_uv_sub = gnt.nodes.new("ShaderNodeMath")
    pal_flip_uv_sub.operation = "SUBTRACT"
    pal_flip_uv_sub.inputs[1].default_value = 1.0
    pal_flip_uv_mult = gnt.nodes.new("ShaderNodeMath")
    pal_flip_uv_mult.operation = "MULTIPLY"
    pal_flip_uv_mult.inputs[1].default_value = -1.0

    gnt.links.new(input.outputs["Palette (Preview)"], pal_add.inputs[1])
    gnt.links.new(pal_add.outputs[0], pal_div.inputs[0])
    gnt.links.new(pal_img_info.outputs["Height"], pal_div.inputs[1])
    gnt.links.new(pal_div.outputs[0], pal_flip_uv_sub.inputs[0])
    gnt.links.new(pal_flip_uv_sub.outputs[0], pal_flip_uv_mult.inputs[0])

    # create and link vector
    comb = gnt.nodes.new("ShaderNodeCombineXYZ")
    gnt.links.new(mathns[8].outputs[0], comb.inputs[0])
    gnt.links.new(pal_flip_uv_mult.outputs[0], comb.inputs[1])
    gnt.links.new(comb.outputs[0], cptn.inputs["Value"])

    return gnt


def create_image_node(node_tree, param) -> bpy.types.ShaderNodeTexImage:
    imgnode = node_tree.nodes.new("ShaderNodeTexImage")
    imgnode.name = param.name
    imgnode.label = param.name
    imgnode.is_sollumz = True
    return imgnode


def create_parameter_node(
    node_tree: bpy.types.NodeTree,
    param: (
        ShaderParameterFloatDef | ShaderParameterFloat2Def | ShaderParameterFloat3Def | ShaderParameterFloat4Def |
        ShaderParameterFloat4x4Def
    )
) -> SzShaderNodeParameter:
    node: SzShaderNodeParameter = node_tree.nodes.new(SzShaderNodeParameter.bl_idname)
    node.name = param.name
    node.label = node.name

    display_type = SzShaderNodeParameterDisplayType.DEFAULT
    match param.type:
        case ShaderParameterType.FLOAT:
            cols, rows = 1, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.BOOL:
                display_type = SzShaderNodeParameterDisplayType.BOOL
        case ShaderParameterType.FLOAT2:
            cols, rows = 2, max(1, param.count)
        case ShaderParameterType.FLOAT3:
            cols, rows = 3, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.RGB:
                display_type = SzShaderNodeParameterDisplayType.RGB
        case ShaderParameterType.FLOAT4:
            cols, rows = 4, max(1, param.count)
            if param.count == 0 and param.subtype == ShaderParameterSubtype.RGBA:
                display_type = SzShaderNodeParameterDisplayType.RGBA
        case ShaderParameterType.FLOAT4X4:
            cols, rows = 4, 4

    if param.hidden:
        display_type = SzShaderNodeParameterDisplayType.HIDDEN_IN_UI

    node.set_size(cols, rows)
    node.set_display_type(display_type)

    if rows == 1 and param.type in {ShaderParameterType.FLOAT, ShaderParameterType.FLOAT2,
                                    ShaderParameterType.FLOAT3, ShaderParameterType.FLOAT4}:
        node.set("X", param.x)
        if cols > 1:
            node.set("Y", param.y)
        if cols > 2:
            node.set("Z", param.z)
        if cols > 3:
            node.set("W", param.w)

    return node


def link_diffuse(b: ShaderBuilder, imgnode):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    links.new(imgnode.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(imgnode.outputs["Alpha"], bsdf.inputs["Alpha"])


def link_diffuses(b: ShaderBuilder, tex1, tex2):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    rgb = node_tree.nodes.new("ShaderNodeMixRGB")
    links.new(tex1.outputs["Color"], rgb.inputs["Color1"])
    links.new(tex2.outputs["Color"], rgb.inputs["Color2"])
    links.new(tex2.outputs["Alpha"], rgb.inputs["Fac"])
    links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])
    return rgb


def link_detailed_normal(b: ShaderBuilder, bumptex, dtltex, spectex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    dtltex2 = node_tree.nodes.new("ShaderNodeTexImage")
    dtltex2.name = "Extra"
    dtltex2.label = dtltex2.name
    ds = node_tree.nodes["detailSettings"]
    links = node_tree.links
    uv_map0 = node_tree.nodes[get_uv_map_name(0)]
    comxyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
    mathns = []
    for _ in range(9):
        math = node_tree.nodes.new("ShaderNodeVectorMath")
        mathns.append(math)
    nrm = node_tree.nodes.new("ShaderNodeNormalMap")

    links.new(uv_map0.outputs[0], mathns[0].inputs[0])

    links.new(ds.outputs["Z"], comxyz.inputs[0])
    links.new(ds.outputs["W"], comxyz.inputs[1])

    mathns[0].operation = "MULTIPLY"
    links.new(comxyz.outputs[0], mathns[0].inputs[1])
    links.new(mathns[0].outputs[0], dtltex2.inputs[0])

    mathns[1].operation = "MULTIPLY"
    mathns[1].inputs[1].default_value[0] = 3.17
    mathns[1].inputs[1].default_value[1] = 3.17
    links.new(mathns[0].outputs[0], mathns[1].inputs[0])
    links.new(mathns[1].outputs[0], dtltex.inputs[0])

    mathns[2].operation = "SUBTRACT"
    mathns[2].inputs[1].default_value[0] = 0.5
    mathns[2].inputs[1].default_value[1] = 0.5
    links.new(dtltex.outputs[0], mathns[2].inputs[0])

    mathns[3].operation = "SUBTRACT"
    mathns[3].inputs[1].default_value[0] = 0.5
    mathns[3].inputs[1].default_value[1] = 0.5
    links.new(dtltex2.outputs[0], mathns[3].inputs[0])

    mathns[4].operation = "ADD"
    links.new(mathns[2].outputs[0], mathns[4].inputs[0])
    links.new(mathns[3].outputs[0], mathns[4].inputs[1])

    mathns[5].operation = "MULTIPLY"
    links.new(mathns[4].outputs[0], mathns[5].inputs[0])
    links.new(ds.outputs["Y"], mathns[5].inputs[1])

    mathns[6].operation = "MULTIPLY"
    if spectex:
        links.new(spectex.outputs[1], mathns[6].inputs[0])
    links.new(mathns[5].outputs[0], mathns[6].inputs[1])

    mathns[7].operation = "MULTIPLY"
    mathns[7].inputs[1].default_value[0] = 1
    mathns[7].inputs[1].default_value[1] = 1
    links.new(mathns[6].outputs[0], mathns[7].inputs[0])

    mathns[8].operation = "ADD"
    links.new(mathns[7].outputs[0], mathns[8].inputs[0])
    links.new(bumptex.outputs[0], mathns[8].inputs[1])

    links.new(mathns[8].outputs[0], nrm.inputs[1])
    links.new(nrm.outputs[0], bsdf.inputs["Normal"])


def link_normal(b: ShaderBuilder, nrmtex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    normalmap = node_tree.nodes.new("ShaderNodeNormalMap")

    rgb_curves = create_normal_invert_node(node_tree)

    links.new(nrmtex.outputs["Color"], rgb_curves.inputs["Color"])
    links.new(rgb_curves.outputs["Color"], normalmap.inputs["Color"])
    links.new(normalmap.outputs["Normal"], bsdf.inputs["Normal"])


def create_normal_invert_node(node_tree: bpy.types.NodeTree):
    """Create RGB curves node that inverts that green channel of normal maps"""
    rgb_curves: bpy.types.ShaderNodeRGBCurve = node_tree.nodes.new(
        "ShaderNodeRGBCurve")

    green_curves = rgb_curves.mapping.curves[1]
    green_curves.points[0].location = (0, 1)
    green_curves.points[1].location = (1, 0)

    return rgb_curves


def link_specular(b: ShaderBuilder, spctex):
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    links.new(spctex.outputs["Color"], bsdf.inputs["Specular IOR Level"])


def create_diff_palette_nodes(
    b: ShaderBuilder,
    palette_tex: bpy.types.ShaderNodeTexImage,
    diffuse_tex: bpy.types.ShaderNodeTexImage
):
    palette_tex.interpolation = "Closest"
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    mathns = []
    locx = 0
    locy = 50
    for _ in range(6):
        math = node_tree.nodes.new("ShaderNodeMath")
        math.location.x = locx
        math.location.y = locy
        mathns.append(math)
        locx += 150
    comxyz = node_tree.nodes.new("ShaderNodeCombineXYZ")

    mathns[0].operation = "MULTIPLY"
    links.new(diffuse_tex.outputs["Alpha"], mathns[0].inputs[0])
    mathns[0].inputs[1].default_value = 255.009995

    mathns[1].operation = "ROUND"
    links.new(mathns[0].outputs[0], mathns[1].inputs[0])

    mathns[2].operation = "SUBTRACT"
    links.new(mathns[1].outputs[0], mathns[2].inputs[0])
    mathns[2].inputs[1].default_value = 32.0

    mathns[3].operation = "MULTIPLY"
    links.new(mathns[2].outputs[0], mathns[3].inputs[0])
    mathns[3].inputs[1].default_value = 0.007813
    links.new(mathns[3].outputs[0], comxyz.inputs[0])

    mathns[4].operation = "MULTIPLY"
    mathns[4].inputs[0].default_value = 0.03125
    mathns[4].inputs[1].default_value = 0.5

    mathns[5].operation = "SUBTRACT"
    mathns[5].inputs[0].default_value = 1
    links.new(mathns[4].outputs[0], mathns[5].inputs[1])
    links.new(mathns[5].outputs[0], comxyz.inputs[1])

    links.new(comxyz.outputs[0], palette_tex.inputs[0])
    links.new(palette_tex.outputs[0], bsdf.inputs["Base Color"])


def create_tint_nodes(
    b: ShaderBuilder,
    diffuse_tex: bpy.types.ShaderNodeTexImage
):
    # create shader attribute node
    # TintColor attribute is filled by tint geometry nodes
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links
    attr = node_tree.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "TintColor"
    mix = node_tree.nodes.new("ShaderNodeMixRGB")
    mix.inputs["Fac"].default_value = 0.95
    mix.blend_type = "MULTIPLY"
    links.new(attr.outputs["Color"], mix.inputs[2])
    links.new(diffuse_tex.outputs[0], mix.inputs[1])
    links.new(mix.outputs[0], bsdf.inputs["Base Color"])


def create_decal_nodes(b: ShaderBuilder, texture, decalflag):
    node_tree = b.node_tree
    output = b.material_output
    bsdf = b.bsdf
    links = node_tree.links
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    trans = node_tree.nodes.new("ShaderNodeBsdfTransparent")
    links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])

    if decalflag == 0:  # cutout
        # Handle alpha test logic for cutout shaders.
        # TODO: alpha test nodes specific to cutout shaders without HardAlphaBlend
        # - trees shaders have AlphaTest and AlphaScale parameters
        # - grass_batch has gAlphaTest parameter
        # - ped_fur? has cutout render bucket but no alpha test-related parameter afaict
        if (
            (hard_alpha_blend := try_get_node(node_tree, "HardAlphaBlend")) and
            isinstance(hard_alpha_blend, SzShaderNodeParameter)
        ):
            # The HardAlphaBlend parameter is used to slightly smooth out the cutout edges.
            # 1.0 = hard edges, 0.0 = softer edges (some transparency in the edges)
            # Negative values invert the cutout but I don't think that's the intended use.
            ALPHA_REF = 90.0 / 255.0
            MIN_ALPHA_REF = 1.0 / 255.0
            sub = node_tree.nodes.new("ShaderNodeMath")
            sub.operation = "SUBTRACT"
            sub.inputs[1].default_value = ALPHA_REF
            div = node_tree.nodes.new("ShaderNodeMath")
            div.operation = "DIVIDE"
            div.inputs[1].default_value = (1.0 - ALPHA_REF) * 0.1
            map_alpha_blend = node_tree.nodes.new("ShaderNodeMapRange")
            map_alpha_blend.clamp = False
            map_alpha_blend.inputs["From Min"].default_value = 0.0
            map_alpha_blend.inputs["From Max"].default_value = 1.0
            alpha_gt = node_tree.nodes.new("ShaderNodeMath")
            alpha_gt.operation = "GREATER_THAN"
            alpha_gt.inputs[1].default_value = MIN_ALPHA_REF
            mul_alpha_test = node_tree.nodes.new("ShaderNodeMath")
            mul_alpha_test.operation = "MULTIPLY"

            links.new(texture.outputs["Alpha"], sub.inputs[0])
            links.new(sub.outputs["Value"], div.inputs[0])
            links.new(hard_alpha_blend.outputs["X"], map_alpha_blend.inputs["Value"])
            links.new(texture.outputs["Alpha"], map_alpha_blend.inputs["To Min"])
            links.new(div.outputs["Value"], map_alpha_blend.inputs["To Max"])
            links.new(map_alpha_blend.outputs["Result"], alpha_gt.inputs[0])
            links.new(map_alpha_blend.outputs["Result"], mul_alpha_test.inputs[0])
            links.new(alpha_gt.outputs["Value"], mul_alpha_test.inputs[1])
            links.new(mul_alpha_test.outputs["Value"], mix.inputs["Fac"])
        else:
            # Fallback to simple alpha test
            # discard if alpha <= 0.5, else opaque
            alpha_gt = node_tree.nodes.new("ShaderNodeMath")
            alpha_gt.operation = "GREATER_THAN"
            alpha_gt.inputs[1].default_value = 0.5
            links.new(texture.outputs["Alpha"], alpha_gt.inputs[0])
            links.new(alpha_gt.outputs["Value"], mix.inputs["Fac"])
    elif decalflag == 1:
        vcs = node_tree.nodes.new("ShaderNodeVertexColor")
        vcs.layer_name = get_color_attr_name(0)
        multi = node_tree.nodes.new("ShaderNodeMath")
        multi.operation = "MULTIPLY"
        links.new(vcs.outputs["Alpha"], multi.inputs[0])
        links.new(texture.outputs["Alpha"], multi.inputs[1])
        links.new(multi.outputs["Value"], mix.inputs["Fac"])
    elif decalflag == 2:  # decal_dirt.sps
        # Here, the diffuse sampler represents an alpha map. DirtDecalMask indicates which channels to consider. Actual
        # color stored in the color0 attribute.
        #   alpha = dot(diffuseColor, DirtDecalMask)
        #   alpha *= color0.a
        #   baseColor = color0.rgb
        dirt_decal_mask_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
        dirt_decal_mask = node_tree.nodes["DirtDecalMask"]
        dot_diffuse_mask = node_tree.nodes.new("ShaderNodeVectorMath")
        dot_diffuse_mask.operation = "DOT_PRODUCT"
        mult_alpha_color0a = node_tree.nodes.new("ShaderNodeMath")
        mult_alpha_color0a.operation = "MULTIPLY"
        color0_attr = node_tree.nodes.new("ShaderNodeVertexColor")
        color0_attr.layer_name = get_color_attr_name(0)

        links.new(dirt_decal_mask.outputs["X"], dirt_decal_mask_xyz.inputs["X"])
        links.new(dirt_decal_mask.outputs["Y"], dirt_decal_mask_xyz.inputs["Y"])
        links.new(dirt_decal_mask.outputs["Z"], dirt_decal_mask_xyz.inputs["Z"])

        links.new(texture.outputs["Color"], dot_diffuse_mask.inputs[0])
        links.new(dirt_decal_mask_xyz.outputs["Vector"], dot_diffuse_mask.inputs[1])

        links.new(dot_diffuse_mask.outputs["Value"], mult_alpha_color0a.inputs[0])
        links.new(color0_attr.outputs["Alpha"], mult_alpha_color0a.inputs[1])

        links.new(mult_alpha_color0a.outputs["Value"], mix.inputs["Fac"])

        links.new(color0_attr.outputs["Color"], bsdf.inputs["Base Color"])
    elif decalflag == 5:  # decal_amb_only.sps
        ambient_decal_mask_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
        ambient_decal_mask = node_tree.nodes["AmbientDecalMask"]
        dot_diffuse_mask = node_tree.nodes.new("ShaderNodeVectorMath")
        dot_diffuse_mask.operation = "DOT_PRODUCT"
        mult_alpha_color0a = node_tree.nodes.new("ShaderNodeMath")
        mult_alpha_color0a.operation = "MULTIPLY"
        color0_attr = node_tree.nodes.new("ShaderNodeVertexColor")
        invert_color = node_tree.nodes.new("ShaderNodeInvert")
        color0_attr.layer_name = get_color_attr_name(0)

        links.new(ambient_decal_mask.outputs["X"], ambient_decal_mask_xyz.inputs["X"])
        links.new(ambient_decal_mask.outputs["Y"], ambient_decal_mask_xyz.inputs["Y"])
        links.new(ambient_decal_mask.outputs["Z"], ambient_decal_mask_xyz.inputs["Z"])

        links.new(texture.outputs["Color"], invert_color.inputs[1])
        links.new(invert_color.outputs["Color"], dot_diffuse_mask.inputs[0])
        links.new(ambient_decal_mask_xyz.outputs["Vector"], dot_diffuse_mask.inputs[1])

        links.new(dot_diffuse_mask.outputs["Value"], mult_alpha_color0a.inputs[0])
        links.new(color0_attr.outputs["Alpha"], mult_alpha_color0a.inputs[1])

        links.new(mult_alpha_color0a.outputs["Value"], mix.inputs["Fac"])

        links.new(color0_attr.outputs["Color"], bsdf.inputs["Base Color"])

    links.new(trans.outputs["BSDF"], mix.inputs[1])
    links.remove(bsdf.outputs["BSDF"].links[0])
    links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])


def create_distance_map_nodes(b: ShaderBuilder, distance_map_texture: bpy.types.ShaderNodeTexImage):
    node_tree = b.node_tree
    output = b.material_output
    bsdf = b.bsdf
    links = node_tree.links
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    trans = node_tree.nodes.new("ShaderNodeBsdfTransparent")
    multiply_color = node_tree.nodes.new("ShaderNodeVectorMath")
    multiply_color.operation = "MULTIPLY"
    multiply_alpha = node_tree.nodes.new("ShaderNodeMath")
    multiply_alpha.operation = "MULTIPLY"
    multiply_alpha.inputs[1].default_value = 1.0  # alpha value
    distance_greater_than = node_tree.nodes.new("ShaderNodeMath")
    distance_greater_than.operation = "GREATER_THAN"
    distance_greater_than.inputs[1].default_value = 0.5  # distance threshold
    distance_separate_x = node_tree.nodes.new("ShaderNodeSeparateXYZ")
    fill_color_combine = node_tree.nodes.new("ShaderNodeCombineXYZ")
    fill_color = node_tree.nodes["fillColor"]

    # combine fillColor into a vector
    links.new(fill_color.outputs["X"], fill_color_combine.inputs["X"])
    links.new(fill_color.outputs["Y"], fill_color_combine.inputs["Y"])
    links.new(fill_color.outputs["Z"], fill_color_combine.inputs["Z"])

    # extract distance value from texture and check > 0.5
    links.new(distance_map_texture.outputs["Color"], distance_separate_x.inputs["Vector"])
    links.remove(distance_map_texture.outputs["Alpha"].links[0])
    links.new(distance_separate_x.outputs["X"], distance_greater_than.inputs["Value"])

    # multiply color and alpha by distance check result
    links.new(distance_greater_than.outputs["Value"], multiply_alpha.inputs[0])
    links.new(distance_greater_than.outputs["Value"], multiply_color.inputs[0])
    links.new(fill_color_combine.outputs["Vector"], multiply_color.inputs[1])

    # connect output color and alpha
    links.new(multiply_alpha.outputs["Value"], mix.inputs["Fac"])
    links.new(multiply_color.outputs["Vector"], bsdf.inputs["Base Color"])

    # connect BSDFs and material output
    links.new(trans.outputs["BSDF"], mix.inputs[1])
    links.remove(bsdf.outputs["BSDF"].links[0])
    links.new(bsdf.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])


def create_emissive_nodes(b: ShaderBuilder):
    node_tree = b.node_tree
    links = node_tree.links
    output = b.material_output
    tmpn = output.inputs[0].links[0].from_node
    mix = node_tree.nodes.new("ShaderNodeMixShader")
    if tmpn == b.bsdf:
        em = node_tree.nodes.new("ShaderNodeEmission")
        diff = node_tree.nodes["DiffuseSampler"]
        links.new(diff.outputs[0], em.inputs[0])
        links.new(em.outputs[0], mix.inputs[1])
        links.new(tmpn.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs[0])


def link_value_shader_parameters(b: ShaderBuilder):
    shader = b.shader
    node_tree = b.node_tree
    links = node_tree.links

    bsdf = b.bsdf
    bmp = None
    spec_im = None
    spec_fm = None
    em_m = None
    spec_m = None

    for param in shader.parameters:
        if param.name == "bumpiness":
            bmp = node_tree.nodes["bumpiness"]
        elif param.name == "specularIntensityMult":
            spec_im = node_tree.nodes["specularIntensityMult"]
        elif param.name == "specularFalloffMult":
            spec_fm = node_tree.nodes["specularFalloffMult"]
        elif param.name == "emissiveMultiplier":
            em_m = node_tree.nodes["emissiveMultiplier"]
        elif param.name == "specMapIntMask":
            spec_m = node_tree.nodes["specMapIntMask"]

    if bmp:
        nm = try_get_node_by_cls(node_tree, bpy.types.ShaderNodeNormalMap)
        if nm:
            links.new(bmp.outputs["X"], nm.inputs[0])
    if spec_im:
        spec = try_get_node(node_tree, "SpecSampler")
        if spec:
            map = node_tree.nodes.new("ShaderNodeMapRange")
            map.inputs[2].default_value = 1
            map.inputs[4].default_value = 1
            map.clamp = True
            mult = node_tree.nodes.new("ShaderNodeMath")
            mult.operation = "MULTIPLY"
            if spec_m:
                dot_prod = node_tree.nodes.new("ShaderNodeVectorMath")
                dot_prod.operation = "DOT_PRODUCT"
                links.new(dot_prod.inputs[0], spec.outputs[0])
                combine_xyz = node_tree.nodes.new("ShaderNodeCombineXYZ")
                spec_mask = try_get_node(node_tree, "specMapIntMask")
                links.new(spec_mask.outputs["X"], combine_xyz.inputs["X"])
                links.new(spec_mask.outputs["Y"], combine_xyz.inputs["Y"])
                links.new(spec_mask.outputs["Z"], combine_xyz.inputs["Z"])
                links.new(combine_xyz.outputs[0], dot_prod.inputs[1])
                links.new(dot_prod.outputs["Value"], mult.inputs[0])
                links.new(map.outputs[0], mult.inputs[1])
                links.new(spec_im.outputs["X"], map.inputs[0])
                links.new(mult.outputs[0], bsdf.inputs["Specular IOR Level"])
            else:
                links.new(spec.outputs[0], mult.inputs[0])
                links.new(map.outputs[0], mult.inputs[1])
                links.new(spec_im.outputs["X"], map.inputs[0])
                links.new(mult.outputs[0], bsdf.inputs["Specular IOR Level"])

    if spec_fm:
        map = node_tree.nodes.new("ShaderNodeMapRange")
        map.inputs[2].default_value = 512
        map.inputs[3].default_value = 1
        map.inputs[4].default_value = 0
        map.clamp = True
        links.new(spec_fm.outputs["X"], map.inputs[0])
        links.new(map.outputs[0], bsdf.inputs["Roughness"])
    if em_m:
        em = try_get_node_by_cls(node_tree, bpy.types.ShaderNodeEmission)
        if em:
            links.new(em_m.outputs["X"], em.inputs[1])


def create_water_nodes(b: ShaderBuilder):
    node_tree = b.node_tree
    links = node_tree.links
    bsdf = b.bsdf
    output = b.material_output

    bsdf.inputs["Base Color"].default_value = (0.602416, 0.894181, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.444
    bsdf.inputs["Transmission Weight"].default_value = 1.0

    nm = node_tree.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.2
    noise = node_tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 5.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 2.0
    layer_weight = node_tree.nodes.new("ShaderNodeLayerWeight")
    layer_weight.inputs["Blend"].default_value = 0.94

    links.new(layer_weight.outputs["Fresnel"], bsdf.inputs["Alpha"])
    links.new(noise.outputs["Color"], nm.inputs["Color"])
    links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])


def create_basic_shader_nodes(b: ShaderBuilder):
    shader = b.shader
    filename = b.filename
    mat = b.material
    node_tree = b.node_tree
    bsdf = b.bsdf

    texture = None
    texture2 = None
    tintpal = None
    diffpal = None
    bumptex = None
    spectex = None
    detltex = None
    is_distance_map = False

    for param in shader.parameters:
        match param.type:
            case ShaderParameterType.TEXTURE:
                imgnode = create_image_node(node_tree, param)
                if param.name in ("DiffuseSampler", "PlateBgSampler"):
                    texture = imgnode
                elif param.name in ("BumpSampler", "PlateBgBumpSampler"):
                    bumptex = imgnode
                elif param.name == "SpecSampler":
                    spectex = imgnode
                elif param.name == "DetailSampler":
                    detltex = imgnode
                elif param.name == "TintPaletteSampler":
                    tintpal = imgnode
                elif param.name == "TextureSamplerDiffPal":
                    diffpal = imgnode
                elif param.name == "distanceMapSampler":
                    texture = imgnode
                    is_distance_map = True
                elif param.name in ("DiffuseSampler2", "DiffuseExtraSampler"):
                    texture2 = imgnode
                else:
                    if not texture:
                        texture = imgnode
            case (ShaderParameterType.FLOAT |
                  ShaderParameterType.FLOAT2 |
                  ShaderParameterType.FLOAT3 |
                  ShaderParameterType.FLOAT4 |
                  ShaderParameterType.FLOAT4X4):
                create_parameter_node(node_tree, param)
            case _:
                raise Exception(f"Unknown shader parameter! {param.type=} {param.name=}")

    use_diff = True if texture else False
    use_diff2 = True if texture2 else False
    use_bump = True if bumptex else False
    use_spec = True if spectex else False
    use_detl = True if detltex else False
    use_tint = True if tintpal else False

    # Some shaders have TextureSamplerDiffPal but don't actually use it, so we only create palette
    # shader nodes on the specific shaders that use it
    use_palette = diffpal is not None and filename in ShaderManager.palette_shaders

    use_decal = shader.is_alpha or shader.is_decal or shader.is_cutout
    decalflag = 0
    blend_mode = "OPAQUE"
    if use_decal:
        # set blend mode
        if shader.is_cutout:
            blend_mode = "CLIP"
        else:
            blend_mode = "BLEND"
            decalflag = 1
        # set flags
        if filename == "decal_dirt.sps":
            decalflag = 2
        elif filename in {"decal_normal_only.sps", "mirror_decal.sps", "reflect_decal.sps"}:
            decalflag = 3
        elif filename in {"decal_spec_only.sps", "spec_decal.sps"}:
            decalflag = 4
        elif filename == "decal_amb_only.sps":
            decalflag = 5
        elif filename in {"vehicle_badges.sps", "vehicle_decal.sps"}:
            decalflag = 1  # badges and decals need to multiply the texture alpha by the Color 1 Alpha component
        elif filename.startswith("vehicle_"):
            # Don't treat any other alpha vehicle shaders as decals (e.g. lightsemissive or vehglass).
            # Particularly problematic with lightsemissive as Color 1 Alpha component contains the light ID,
            # which previously was being incorrectly used to multiply the texture alpha.
            use_decal = False

    is_emissive = True if filename in ShaderManager.em_shaders else False

    if not use_decal:
        if use_diff:
            if use_diff2:
                link_diffuses(b, texture, texture2)
            else:
                link_diffuse(b, texture)
    else:
        create_decal_nodes(b, texture, decalflag)

    if use_bump:
        if use_detl:
            link_detailed_normal(b, bumptex, detltex, spectex)
        else:
            link_normal(b, bumptex)
    if use_spec:
        link_specular(b, spectex)
    else:
        bsdf.inputs["Specular IOR Level"].default_value = 0

    if use_tint:
        create_tint_nodes(b, texture)

    if use_palette:
        create_diff_palette_nodes(b, diffpal, texture)

    if is_emissive:
        create_emissive_nodes(b)

    is_water = filename in ShaderManager.water_shaders
    if is_water:
        create_water_nodes(b)

    if is_distance_map:
        blend_mode = "BLEND"
        create_distance_map_nodes(b, texture)

    is_veh_shader = filename in ShaderManager.veh_paints
    if is_veh_shader:
        bsdf.inputs["Metallic"].default_value = 1.0
        bsdf.inputs["Coat Weight"].default_value = 1.0

    # link value parameters
    link_value_shader_parameters(b)

    if bpy.app.version < (4, 2, 0):
        mat.blend_method = blend_mode
    else:
        mat.surface_render_method = "BLENDED" if blend_mode != "OPAQUE" else "DITHERED"


def create_terrain_shader(b: ShaderBuilder):
    shader = b.shader
    node_tree = b.node_tree
    bsdf = b.bsdf
    links = node_tree.links

    ts1 = None
    ts2 = None
    ts3 = None
    ts4 = None
    bs1 = None
    bs2 = None
    bs3 = None
    bs4 = None
    tm = None

    for param in shader.parameters:
        match param.type:
            case ShaderParameterType.TEXTURE:
                imgnode = create_image_node(node_tree, param)
                if param.name == "TextureSampler_layer0":
                    ts1 = imgnode
                elif param.name == "TextureSampler_layer1":
                    ts2 = imgnode
                elif param.name == "TextureSampler_layer2":
                    ts3 = imgnode
                elif param.name == "TextureSampler_layer3":
                    ts4 = imgnode
                elif param.name == "BumpSampler_layer0":
                    bs1 = imgnode
                elif param.name == "BumpSampler_layer1":
                    bs2 = imgnode
                elif param.name == "BumpSampler_layer2":
                    bs3 = imgnode
                elif param.name == "BumpSampler_layer3":
                    bs4 = imgnode
                elif param.name == "lookupSampler":
                    tm = imgnode
            case (ShaderParameterType.FLOAT |
                  ShaderParameterType.FLOAT2 |
                  ShaderParameterType.FLOAT3 |
                  ShaderParameterType.FLOAT4 |
                  ShaderParameterType.FLOAT4X4):
                create_parameter_node(node_tree, param)
            case _:
                raise Exception(f"Unknown shader parameter! {param.type=} {param.name=}")

    mixns = []
    for _ in range(8 if tm else 7):
        mix = node_tree.nodes.new("ShaderNodeMixRGB")
        mixns.append(mix)

    seprgb = node_tree.nodes.new("ShaderNodeSeparateRGB")
    if shader.is_terrain_mask_only:
        links.new(tm.outputs[0], seprgb.inputs[0])
    else:
        attr_c1 = node_tree.nodes.new("ShaderNodeAttribute")
        attr_c1.attribute_name = get_color_attr_name(1)
        links.new(attr_c1.outputs[0], mixns[0].inputs[1])
        links.new(attr_c1.outputs[0], mixns[0].inputs[2])

        attr_c0 = node_tree.nodes.new("ShaderNodeAttribute")
        attr_c0.attribute_name = get_color_attr_name(0)
        links.new(attr_c0.outputs[3], mixns[0].inputs[0])
        links.new(mixns[0].outputs[0], seprgb.inputs[0])

    # t1 / t2
    links.new(seprgb.outputs[2], mixns[1].inputs[0])
    links.new(ts1.outputs[0], mixns[1].inputs[1])
    links.new(ts2.outputs[0], mixns[1].inputs[2])

    # t3 / t4
    links.new(seprgb.outputs[2], mixns[2].inputs[0])
    links.new(ts3.outputs[0], mixns[2].inputs[1])
    links.new(ts4.outputs[0], mixns[2].inputs[2])

    links.new(seprgb.outputs[1], mixns[3].inputs[0])
    links.new(mixns[1].outputs[0], mixns[3].inputs[1])
    links.new(mixns[2].outputs[0], mixns[3].inputs[2])

    links.new(mixns[3].outputs[0], bsdf.inputs["Base Color"])

    if bs1:
        links.new(seprgb.outputs[2], mixns[4].inputs[0])
        links.new(bs1.outputs[0], mixns[4].inputs[1])
        links.new(bs2.outputs[0], mixns[4].inputs[2])

        links.new(seprgb.outputs[2], mixns[5].inputs[0])
        links.new(bs3.outputs[0], mixns[5].inputs[1])
        links.new(bs4.outputs[0], mixns[5].inputs[2])

        links.new(seprgb.outputs[1], mixns[6].inputs[0])
        links.new(mixns[4].outputs[0], mixns[6].inputs[1])
        links.new(mixns[5].outputs[0], mixns[6].inputs[2])

        nrm = node_tree.nodes.new("ShaderNodeNormalMap")
        links.new(mixns[6].outputs[0], nrm.inputs[1])
        links.new(nrm.outputs[0], bsdf.inputs["Normal"])

    # assign lookup sampler last so that it overwrites any socket connections
    if tm:
        uv_map1 = node_tree.nodes[get_uv_map_name(1)]
        links.new(uv_map1.outputs[0], tm.inputs[0])
        links.new(tm.outputs[0], mixns[0].inputs[1])

    # link value parameters
    bsdf.inputs["Specular IOR Level"].default_value = 0
    link_value_shader_parameters(b)


def create_uv_map_nodes(b: ShaderBuilder):
    """Creates a ``ShaderNodeUVMap`` node for each UV map used in the shader."""
    shader = b.shader
    node_tree = b.node_tree

    used_uv_maps = set(shader.uv_maps.values())
    for uv_map_index in used_uv_maps:
        uv_map = get_uv_map_name(uv_map_index)
        node = node_tree.nodes.new("ShaderNodeUVMap")
        node.name = uv_map
        node.label = uv_map
        node.uv_map = uv_map


def link_uv_map_nodes_to_textures(b: ShaderBuilder):
    """For each texture node, links the corresponding UV map to its input UV if it hasn't been linked already."""
    shader = b.shader
    node_tree = b.node_tree

    for tex_name, uv_map_index in shader.uv_maps.items():
        tex_node = node_tree.nodes[tex_name]
        uv_map_node = node_tree.nodes[get_uv_map_name(uv_map_index)]

        if tex_node.inputs[0].is_linked:
            # texture already linked when creating the node tree, skip it
            continue

        node_tree.links.new(uv_map_node.outputs[0], tex_node.inputs[0])


def create_shader(filename: str, in_place_material: Optional[bpy.types.Material] = None) -> bpy.types.Material:
    # from ..sollumz_preferences import get_addon_preferences
    # preferences = get_addon_preferences(bpy.context)
    # if preferences.experimental_shader_expressions:
    #     from .shader_materials_v2 import create_shader
    #     return create_shader(filename)

    shader = ShaderManager.find_shader(filename)
    if shader is None:
        raise AttributeError(f"Shader '{filename}' does not exist!")

    filename = shader.filename  # in case `filename` was hashed initially
    base_name = ShaderManager.find_shader_base_name(filename)
    material_name = filename.replace(".sps", "")

    if in_place_material and in_place_material.use_nodes:
        # If creating the shader in an existing material, setup the node tree to its default state
        current_node_tree = in_place_material.node_tree
        current_node_tree.nodes.clear()
        material_ouput = current_node_tree.nodes.new("ShaderNodeOutputMaterial")
        bsdf = current_node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        current_node_tree.links.new(bsdf.outputs["BSDF"], material_ouput.inputs["Surface"])

    mat = in_place_material or bpy.data.materials.new(material_name)
    mat.sollum_type = MaterialType.SHADER
    mat.use_nodes = True
    mat.shader_properties.name = base_name
    mat.shader_properties.filename = filename
    mat.shader_properties.renderbucket = RenderBucket(shader.render_bucket).name

    bsdf, material_output = find_bsdf_and_material_output(mat)
    assert material_output is not None, "ShaderNodeOutputMaterial not found in default node_tree!"
    assert bsdf is not None, "ShaderNodeBsdfPrincipled not found in default node_tree!"

    builder = ShaderBuilder(shader=shader,
                            filename=filename,
                            material=mat,
                            node_tree=mat.node_tree,
                            material_output=material_output,
                            bsdf=bsdf)

    create_uv_map_nodes(builder)

    if shader.is_terrain:
        create_terrain_shader(builder)
    else:
        create_basic_shader_nodes(builder)

    if shader.is_uv_animation_supported:
        add_global_anim_uv_nodes(mat)

    if shader.filename.startswith("vehicle_"):
        # Add additionals node to support vehicle render preview features
        if shader.filename == "vehicle_lightsemissive.sps":
            add_vehicle_lights_emissive_toggle_nodes(builder)

        if "matDiffuseColor" in shader.parameter_map:
            add_vehicle_body_color_nodes(builder)

        if "DirtSampler" in shader.parameter_map:
            add_vehicle_dirt_nodes(builder)

    link_uv_map_nodes_to_textures(builder)

    organize_node_tree(builder)

    return mat


VEHICLE_PREVIEW_NODE_LIGHT_EMISSIVE_TOGGLE = [
    f"PreviewLightID{light_id}Toggle" for light_id in range(MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID+1)
]
VEHICLE_PREVIEW_NODE_BODY_COLOR = [
    f"PreviewBodyColor{paint_layer_id}" for paint_layer_id in range(8)
]
VEHICLE_PREVIEW_NODE_DIRT_LEVEL = "PreviewDirtLevel"
VEHICLE_PREVIEW_NODE_DIRT_WETNESS = "PreviewDirtWetness"
VEHICLE_PREVIEW_NODE_DIRT_COLOR = "PreviewDirtColor"


def add_vehicle_lights_emissive_toggle_nodes(builder: ShaderBuilder):
    em = try_get_node_by_cls(builder.node_tree, bpy.types.ShaderNodeEmission)
    if not em:
        return

    shader_expr = vehicle_lights_emissive_toggles()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    builder.node_tree.links.new(compiled_shader_expr.output, em.inputs["Strength"])


def vehicle_lights_emissive_toggles() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        color_attribute,
        float_param,
        value,
    )

    attr_c0 = color_attribute(get_color_attr_name(0))
    emissive_mult = float_param("emissiveMultiplier")

    eps = 0.001
    final_flag = 0.0
    for light_id in range(MIN_VEHICLE_LIGHT_ID, MAX_VEHICLE_LIGHT_ID+1):
        light_id_normalized = light_id / 255
        flag_toggle = value(VEHICLE_PREVIEW_NODE_LIGHT_EMISSIVE_TOGGLE[light_id], default_value=1.0)
        flag_lower_bound = attr_c0.alpha > (light_id_normalized - eps)
        flag_upper_bound = attr_c0.alpha < (light_id_normalized + eps)
        flag = flag_toggle * flag_lower_bound * flag_upper_bound
        final_flag += flag

    final_mult = emissive_mult * final_flag
    return final_mult


def add_vehicle_dirt_nodes(builder: ShaderBuilder):
    shader_expr = vehicle_dirt_overlay()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    orig_base_color = builder.bsdf.inputs["Base Color"].links[0].from_socket
    builder.node_tree.links.new(orig_base_color, compiled_shader_expr.node.inputs["A"])
    builder.node_tree.links.new(compiled_shader_expr.output, builder.bsdf.inputs["Base Color"])


def vehicle_dirt_overlay() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        tex,
        value,
        vec,
        vec_value,
        mix_color,
        map_range,
    )

    # Shader parameters 'dirtLevelMod' and 'dirtColor' are set at runtime. So ignore them and instead use our own values
    dirt_color = vec_value(VEHICLE_PREVIEW_NODE_DIRT_COLOR, default_value=(70/255, 60/255, 50/255))
    dirt_level = value(VEHICLE_PREVIEW_NODE_DIRT_LEVEL, default_value=0.0)
    dirt_wetness = value(VEHICLE_PREVIEW_NODE_DIRT_WETNESS, default_value=0.0)

    dirt_tex = tex("DirtSampler", None)  # will be linked to the correct UV map by `link_uv_map_nodes_to_textures`

    dirt_level = dirt_level * map_range(
        dirt_wetness,
        0.0, 1.0,
        dirt_tex.color.r, dirt_tex.color.g
    )

    dirt_mod = map_range(dirt_wetness, 0.0, 1.0, 1.0, 0.6)

    dirt_color = dirt_color * dirt_mod

    # this vec(0) will be replaced by the shader base color
    final_color = mix_color(vec(0.0, 0.0, 0.0), dirt_color, dirt_level)

    # TODO: increase alpha on vehglass

    return final_color


def add_vehicle_body_color_nodes(builder: ShaderBuilder):
    shader_expr = vehicle_body_color()
    compiled_shader_expr = compile_expr(builder.material.node_tree, shader_expr)

    orig_base_color = builder.bsdf.inputs["Base Color"].links[0].from_socket
    builder.node_tree.links.new(orig_base_color, compiled_shader_expr.node.inputs[0])
    builder.node_tree.links.new(compiled_shader_expr.output, builder.bsdf.inputs["Base Color"])


def vehicle_body_color() -> expr.ShaderExpr:
    from ..shared.shader_expr.builtins import (
        param,
        vec,
        vec_value,
    )

    mat_diffuse_color = param("matDiffuseColor").vec

    final_paint_layer_color = vec(0.0, 0.0, 0.0)
    eps = 0.0001
    enable_paint_layer = (mat_diffuse_color.x > (2.0 - eps)) * (mat_diffuse_color.x < (2.0 + eps))
    for paint_layer_id in range(1, 7+1):
        default_color = (1.0, 1.0, 1.0)
        if paint_layer_id == 5:
            default_color = (0.5, 0.5, 0.5)
        body_color = vec_value(VEHICLE_PREVIEW_NODE_BODY_COLOR[paint_layer_id], default_value=default_color)

        use_this_paint_layer = (mat_diffuse_color.y > (paint_layer_id - eps)) * \
            (mat_diffuse_color.y < (paint_layer_id + eps))

        final_paint_layer_color += body_color * use_this_paint_layer

    final_body_color = final_paint_layer_color * enable_paint_layer + mat_diffuse_color * (1.0 - enable_paint_layer)

    return vec(1.0, 1.0, 1.0) * final_body_color  # this vec(1) will be replaced by the shader base color
