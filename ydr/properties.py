import bpy
from ..sollumz_properties import SOLLUMZ_UI_NAMES, items_from_enums, TextureUsage, TextureFormat, LODLevel, SollumType, LightType, FlagPropertyGroup, TimeFlags
from ..ydr.shader_materials import shadermats, ShaderMaterial
from bpy.app.handlers import persistent
from bpy.path import basename


class DrawableProperties(bpy.types.PropertyGroup):
    lod_dist_high: bpy.props.FloatProperty(
        min=0, max=10000, default=9998, name="Lod Distance High")
    lod_dist_med: bpy.props.FloatProperty(
        min=0, max=10000, default=9998, name="Lod Distance Med")
    lod_dist_low: bpy.props.FloatProperty(
        min=0, max=10000, default=9998, name="Lod Distance Low")
    lod_dist_vlow: bpy.props.FloatProperty(
        min=0, max=10000, default=9998, name="Lod Distance Vlow")
    unknown_9A: bpy.props.FloatProperty(
        min=0, max=10000, default=9998, name="Unknown 9A")


class DrawableModelProperties(bpy.types.PropertyGroup):
    render_mask: bpy.props.IntProperty(name="Render Mask", default=255)
    flags: bpy.props.IntProperty(name="Flags", default=0)
    unknown_1: bpy.props.IntProperty(name="Unknown 1", default=0)
    sollum_lod: bpy.props.EnumProperty(
        items=items_from_enums(LODLevel),
        name="LOD Level",
        default="sollumz_high"
    )


class ShaderProperties(bpy.types.PropertyGroup):
    renderbucket: bpy.props.IntProperty(name="Render Bucket", default=0)
    filename: bpy.props.StringProperty(
        name="Shader Filename", default="default.sps")
    name: bpy.props.StringProperty(name="Shader Name", default="default")


class TextureFlags(bpy.types.PropertyGroup):
    not_half: bpy.props.BoolProperty(name="NOT_HALF", default=False)
    hd_split: bpy.props.BoolProperty(name="HD_SPLIT", default=False)
    x2: bpy.props.BoolProperty(name="X2", default=False)
    x4: bpy.props.BoolProperty(name="X4", default=False)
    y4: bpy.props.BoolProperty(name="Y4", default=False)
    x8: bpy.props.BoolProperty(name="X8", default=False)
    x16: bpy.props.BoolProperty(name="X16", default=False)
    x32: bpy.props.BoolProperty(name="X32", default=False)
    x64: bpy.props.BoolProperty(name="X64", default=False)
    y64: bpy.props.BoolProperty(name="Y64", default=False)
    x128: bpy.props.BoolProperty(name="X128", default=False)
    x256: bpy.props.BoolProperty(name="X256", default=False)
    x512: bpy.props.BoolProperty(name="X512", default=False)
    y512: bpy.props.BoolProperty(name="Y512", default=False)
    x1024: bpy.props.BoolProperty(name="X1024", default=False)
    y1024: bpy.props.BoolProperty(name="Y1024", default=False)
    x2048: bpy.props.BoolProperty(name="X2048", default=False)
    y2048: bpy.props.BoolProperty(name="Y2048", default=False)
    embeddedscriptrt: bpy.props.BoolProperty(
        name="EMBEDDEDSCRIPTRT", default=False)
    unk19: bpy.props.BoolProperty(name="UNK19", default=False)
    unk20: bpy.props.BoolProperty(name="UNK20", default=False)
    unk21: bpy.props.BoolProperty(name="UNK21", default=False)
    flag_full: bpy.props.BoolProperty(name="FLAG_FULL", default=False)
    maps_half: bpy.props.BoolProperty(name="MAPS_HALF", default=False)
    unk24: bpy.props.BoolProperty(name="UNK24", default=False)


def update_property(self, context):
    for area in bpy.context.screen.areas:
        if area.type == 'PROPERTIES':
            for region in area.regions:
                if region.type == 'WINDOW':
                    region.tag_redraw()


class TextureProperties(bpy.types.PropertyGroup):
    embedded: bpy.props.BoolProperty(name="Embedded", default=False, update=update_property)
    usage: bpy.props.EnumProperty(
        items=items_from_enums(TextureUsage),
        name="Usage",
        default=TextureUsage.DIFFUSE
    )

    format: bpy.props.EnumProperty(
        items=items_from_enums(TextureFormat),
        name="Format",
        default=TextureFormat.DXT1
    )

    extra_flags: bpy.props.IntProperty(name="Extra Flags", default=0)


class BoneFlag(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="")


class BoneProperties(bpy.types.PropertyGroup):
    tag: bpy.props.IntProperty(name="BoneTag", default=0, min=0)
    flags: bpy.props.CollectionProperty(type=BoneFlag)
    ul_index: bpy.props.IntProperty(name="UIListIndex", default=0)


class ShaderMaterial(bpy.types.PropertyGroup):
    index: bpy.props.IntProperty("Index")
    name: bpy.props.StringProperty("Name")


class LightProperties(bpy.types.PropertyGroup):
    flashiness: bpy.props.IntProperty(name="Flashiness")
    group_id: bpy.props.IntProperty(name="Group ID")
    falloff: bpy.props.FloatProperty(name="Falloff")
    falloff_exponent: bpy.props.FloatProperty(name="Falloff Exponent")
    culling_plane_normal: bpy.props.FloatVectorProperty(
        name="Culling Plane Normal")
    culling_plane_offset: bpy.props.FloatProperty(name="Culling Plane Offset")
    unknown_45: bpy.props.FloatProperty(name="Unknown 45")
    unknown_46: bpy.props.FloatProperty(name="Unknown 46")
    volume_intensity: bpy.props.FloatProperty(name="Volume Intensity", default=1.0)
    shadow_blur: bpy.props.FloatProperty(name="Shadow Blur")
    volume_size_scale: bpy.props.FloatProperty(name="Volume Size Scale", default=1.0)
    volume_outer_color: bpy.props.FloatVectorProperty(
        name="Volume Outer Color", subtype="COLOR", min=0.0, max=1.0, default=(1.0, 1.0, 1.0))
    light_hash: bpy.props.IntProperty(name="Light Hash")
    volume_outer_intensity: bpy.props.FloatProperty(
        name="Volume Outer Intensity", default=1.0)
    corona_size: bpy.props.FloatProperty(name="Corona Size")
    volume_outer_exponent: bpy.props.FloatProperty(
        name="Volume Outer Exponent", default=1.0)
    light_fade_distance: bpy.props.FloatProperty(name="Light Fade Distance")
    shadow_fade_distance: bpy.props.FloatProperty(name="Shadow Fade Distance")
    specular_fade_distance: bpy.props.FloatProperty(
        name="Specular Fade Distance")
    volumetric_fade_distance: bpy.props.FloatProperty(
        name="Volumetric Fade Distance")
    shadow_near_clip: bpy.props.FloatProperty(name="Shadow Near Clip")
    corona_intensity: bpy.props.FloatProperty(name="Corona Intensity", default=1.0)
    corona_z_bias: bpy.props.FloatProperty(name="Corona Z Bias", default=0.1)
    tangent: bpy.props.FloatVectorProperty(name="Tangent")
    cone_inner_angle: bpy.props.FloatProperty(name="Cone Inner Angle")
    cone_outer_angle: bpy.props.FloatProperty(name="Cone Outer Angle")
    extent: bpy.props.FloatVectorProperty(
        name="Extent", default=(1, 1, 1), subtype="XYZ")
    projected_texture_hash: bpy.props.StringProperty(
        name="Projected Texture Hash")


class LightFlags(FlagPropertyGroup, bpy.types.PropertyGroup):
    unk1: bpy.props.BoolProperty(
        name="Unk1",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk2: bpy.props.BoolProperty(
        name="Unk2",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk3: bpy.props.BoolProperty(
        name="Unk3",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk4: bpy.props.BoolProperty(
        name="Unk4",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk5: bpy.props.BoolProperty(
        name="Ignore Artificial Lights State",
        description="Force light to be on.\nThe native 'SET_ARTIFICIAL_LIGHTS_STATE(BOOL state)' won't affect it",
        update=FlagPropertyGroup.update_flag)
    unk6: bpy.props.BoolProperty(
        name="Unk6",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk7: bpy.props.BoolProperty(
        name="Unk7",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    shadows: bpy.props.BoolProperty(
        name="Shadows Static",
        description="Enable shadows for static entities\nExample: walls, floors, etc..",
        update=FlagPropertyGroup.update_flag)
    shadowd: bpy.props.BoolProperty(
        name="Shadows Dynamic",
        description="Enable shadows for dynamic entities.\nExample: peds, vehicles, etc..",
        update=FlagPropertyGroup.update_flag)
    sunlight: bpy.props.BoolProperty(
        name="Sunlight",
        description="The color and intensity will depend on the time of the day.\nThis will override the light color",
        update=FlagPropertyGroup.update_flag)
    unk11: bpy.props.BoolProperty(
        name="Enable Buzzing",
        description="Not sure what that means? Probably related to the next flag",
        update=FlagPropertyGroup.update_flag)
    electric: bpy.props.BoolProperty(
        name="Electric sound",
        description="Play an electric sound from the light source",
        update=FlagPropertyGroup.update_flag)
    volume: bpy.props.BoolProperty(
        name="Volume",
        description="Force volumetric effect rendering, ignoring timecycle",
        update=FlagPropertyGroup.update_flag)
    specoff: bpy.props.BoolProperty(
        name="No Specular",
        description="Disable specular effect from the light on near surfaces",
        update=FlagPropertyGroup.update_flag)
    unk15: bpy.props.BoolProperty(
        name="Both Interior And Exterior",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    lightoff: bpy.props.BoolProperty(
        name="Corona Only",
        description="Only the corona will be rendered",
        update=FlagPropertyGroup.update_flag)
    prxoff: bpy.props.BoolProperty(
        name="Not In Reflection",
        description="The light won't be visible in reflections, such as mirrors",
        update=FlagPropertyGroup.update_flag)
    unk18: bpy.props.BoolProperty(
        name="Only In Reflection",
        description="The light will only be visible in reflections, such as mirrors",
        update=FlagPropertyGroup.update_flag)
    culling: bpy.props.BoolProperty(
        name="Enable Culling Plane",
        description="Enable the culling plane to cut out the light from the scene.\nMake sure to setup the culling plane settings accordingly",
        update=FlagPropertyGroup.update_flag)
    unk20: bpy.props.BoolProperty(
        name="Enable Volume Outer Color",
        description="Let you control the outer volume color. Otherwise, main color will be used",
        update=FlagPropertyGroup.update_flag)
    unk21: bpy.props.BoolProperty(
        name="Unk21",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk22: bpy.props.BoolProperty(
        name="Unk22",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk23: bpy.props.BoolProperty(
        name="Unk23",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    glassoff: bpy.props.BoolProperty(
        name="Don't Light Alpha",
        description="Light won't affect transparent surfaces, such as glass",
        update=FlagPropertyGroup.update_flag)
    unk25: bpy.props.BoolProperty(
        name="Unk25",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk26: bpy.props.BoolProperty(
        name="Unk26",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk27: bpy.props.BoolProperty(
        name="Unk27",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk28: bpy.props.BoolProperty(
        name="Unk28",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk29: bpy.props.BoolProperty(
        name="Unk29",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk30: bpy.props.BoolProperty(
        name="Unk30",
        description="No description",
        update=FlagPropertyGroup.update_flag)
    unk31: bpy.props.BoolProperty(
        name="Volume only",
        description="Only volumetric will be rendered if the according flag is set.\nCould also be used to disable the light",
        update=FlagPropertyGroup.update_flag)
    unk32: bpy.props.BoolProperty(
        name="Unk32",
        description="No description",
        update=FlagPropertyGroup.update_flag)


# Handler sets the default value of the ShaderMaterials collection on blend file load
@persistent
def on_file_loaded(_):
    bpy.context.scene.shader_materials.clear()
    for index, mat in enumerate(shadermats):
        item = bpy.context.scene.shader_materials.add()
        item.index = index
        item.name = mat.name


def get_light_type(self):
    if self.type == "POINT":
        return 1 if not self.is_capsule else 3
    elif self.type == "SPOT":
        return 2
    else:
        return 0


def set_light_type(self, value):
    if value == 1:
        self.type = "POINT"
        self.is_capsule = False
    elif value == 3:
        self.type = "POINT"
        self.is_capsule = True
    elif value == 2:
        self.type = "SPOT"
        self.is_capsule = False


def get_texture_name(self):
    if self.image:
        return basename(self.image.filepath).split(".")[0]
    return "None"


def register():
    bpy.types.Scene.shader_material_index = bpy.props.IntProperty(
        name="Shader Material Index")  # MAKE ENUM WITH THE MATERIALS NAMES
    bpy.types.Scene.shader_materials = bpy.props.CollectionProperty(
        type=ShaderMaterial, name="Shader Materials")
    bpy.app.handlers.load_post.append(on_file_loaded)
    bpy.types.Object.drawable_properties = bpy.props.PointerProperty(
        type=DrawableProperties)
    bpy.types.Object.drawable_model_properties = bpy.props.PointerProperty(
        type=DrawableModelProperties)
    bpy.types.Material.shader_properties = bpy.props.PointerProperty(
        type=ShaderProperties)
    bpy.types.ShaderNodeTexImage.texture_properties = bpy.props.PointerProperty(
        type=TextureProperties)
    bpy.types.ShaderNodeTexImage.texture_flags = bpy.props.PointerProperty(
        type=TextureFlags)
    bpy.types.ShaderNodeTexImage.sollumz_texture_name = bpy.props.StringProperty(
        name="Texture Name", description="Name of texture.", get=get_texture_name)

    bpy.types.Scene.create_drawable_type = bpy.props.EnumProperty(
        items=[
            (SollumType.DRAWABLE.value,
             SOLLUMZ_UI_NAMES[SollumType.DRAWABLE], "Create a drawable object. (if objects are selected a drawable will be created with them as the children)"),
            (SollumType.DRAWABLE_MODEL.value,
             SOLLUMZ_UI_NAMES[SollumType.DRAWABLE_MODEL], "Create a drawable model object."),
            (SollumType.DRAWABLE_GEOMETRY.value,
             SOLLUMZ_UI_NAMES[SollumType.DRAWABLE_GEOMETRY], "Create a drawable geoemtry object."),
            (SollumType.DRAWABLE_DICTIONARY.value,
             SOLLUMZ_UI_NAMES[SollumType.DRAWABLE_DICTIONARY], "Create a drawable dictionary object."),
        ],
        name="Type",
        default=SollumType.DRAWABLE.value
    )
    bpy.types.Scene.auto_create_embedded_col = bpy.props.BoolProperty(
        name="Auto-Embed Collision", description="Automatically create embedded collision.")

    bpy.types.Bone.bone_properties = bpy.props.PointerProperty(
        type=BoneProperties)
    bpy.types.Light.sollum_type = bpy.props.EnumProperty(
        items=items_from_enums(LightType),
        name="Light Type",
        default=LightType.POINT,
        options={"HIDDEN"},
        get=get_light_type,
        set=set_light_type
    )
    bpy.types.Light.is_capsule = bpy.props.BoolProperty()
    bpy.types.Light.light_properties = bpy.props.PointerProperty(
        type=LightProperties)
    bpy.types.Scene.create_light_type = bpy.props.EnumProperty(
        items=[
            (LightType.POINT.value,
             SOLLUMZ_UI_NAMES[LightType.POINT], SOLLUMZ_UI_NAMES[LightType.POINT]),
            (LightType.SPOT.value,
             SOLLUMZ_UI_NAMES[LightType.SPOT], SOLLUMZ_UI_NAMES[LightType.SPOT]),
            (LightType.CAPSULE.value,
             SOLLUMZ_UI_NAMES[LightType.CAPSULE], SOLLUMZ_UI_NAMES[LightType.CAPSULE]),
        ],
        name="Light Type",
        default=LightType.POINT,
        options={"HIDDEN"}
    )
    bpy.types.Light.time_flags = bpy.props.PointerProperty(type=TimeFlags)
    bpy.types.Light.light_flags = bpy.props.PointerProperty(type=LightFlags)


def unregister():
    del bpy.types.ShaderNodeTexImage.sollumz_texture_name
    del bpy.types.Scene.shader_material_index
    del bpy.types.Scene.shader_materials
    del bpy.types.Object.drawable_properties
    del bpy.types.Object.drawable_model_properties
    del bpy.types.Material.shader_properties
    del bpy.types.ShaderNodeTexImage.texture_properties
    del bpy.types.ShaderNodeTexImage.texture_flags
    del bpy.types.Bone.bone_properties
    del bpy.types.Light.light_properties
    del bpy.types.Scene.create_light_type
    del bpy.types.Light.time_flags
    del bpy.types.Light.light_flags
    del bpy.types.Light.is_capsule
    del bpy.types.Scene.auto_create_embedded_col

    bpy.app.handlers.load_post.remove(on_file_loaded)
