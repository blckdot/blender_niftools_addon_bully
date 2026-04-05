"""This script exports Netimmerse and Gamebryo .nif files from Blender."""

# ***** BEGIN LICENSE BLOCK *****
#
# Copyright © 2007, NIF File Format Library and Tools contributors.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****


import os.path

import bpy
import pyffi.spells.nif.fix
from pyffi.formats.nif import NifFormat

from io_scene_niftools.modules.nif_export.animation.transform import TransformAnimation
from io_scene_niftools.modules.nif_export.constraint import Constraint
from io_scene_niftools.modules.nif_export.block_registry import block_store
from io_scene_niftools.modules.nif_export.object import Object
from io_scene_niftools.modules.nif_export import scene
from io_scene_niftools.modules.nif_export.property.object import ObjectProperty
from io_scene_niftools.nif_common import NifCommon
from io_scene_niftools.utils import math, consts
from io_scene_niftools.utils.singleton import NifOp, EGMData, NifData
from io_scene_niftools.utils.logging import NifLog, NifError


# main export class


class NifExport(NifCommon):

    # TODO: - Expose via properties

    def __init__(self, operator, context):
        NifCommon.__init__(self, operator, context)

        # Helper systems
        self.transform_anim = TransformAnimation()
        self.constrainthelper = Constraint()
        self.objecthelper = Object()
        self.exportable_objects = []
        self.root_objects = []

    def execute(self):
        """Main export function."""
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT', toggle=False)

        NifLog.info(f"Exporting {NifOp.props.filepath}")

        # extract directory, base name, extension
        directory = os.path.dirname(NifOp.props.filepath)
        filebase, fileext = os.path.splitext(os.path.basename(NifOp.props.filepath))

        block_store.block_to_obj = {}  # clear out previous iteration

        try:  # catch export errors

            # protect against null nif versions
            if bpy.context.scene.niftools_scene.game == 'NONE':
                raise NifError("You have not selected a game. Please select a game and"
                                " nif version in the scene tab.")

            # find all objects that do not have a parent
            self.exportable_objects, self.root_objects = self.objecthelper.get_export_objects()
            if not self.exportable_objects:
                NifLog.warn("No objects can be exported!")
                return {'FINISHED'}

            for b_obj in self.exportable_objects:
                if b_obj.type == 'MESH':
                    if b_obj.parent and b_obj.parent.type == 'ARMATURE':
                        for b_mod in b_obj.modifiers:
                            if b_mod.type == 'ARMATURE' and b_mod.use_bone_envelopes:
                                raise NifError(f"'{b_obj.name}': Cannot export envelope skinning. If you have vertex groups, turn off envelopes.\n"
                                               f"If you don't have vertex groups, select the bones one by one press W to "
                                               f"convert their envelopes to vertex weights, and turn off envelopes.")

                # check for non-uniform transforms
                scale = b_obj.scale
                if abs(scale.x - scale.y) > NifOp.props.epsilon or abs(scale.y - scale.z) > NifOp.props.epsilon:
                    NifLog.warn(f"Non-uniform scaling not supported.\n"
                                f"Workaround: apply size and rotation (CTRL-A) on '{b_obj.name}'.")

            b_armature = math.get_armature()
            # some scenes may not have an armature, so nothing to do here
            if b_armature:
                math.set_bone_orientation(b_armature.data.niftools.axis_forward, b_armature.data.niftools.axis_up)

            prefix = "x" if bpy.context.scene.niftools_scene.game in ('MORROWIND', ) else ""
            NifLog.info("Exporting")
            if NifOp.props.animation == 'ALL_NIF':
                NifLog.info("Exporting geometry and animation")
            elif NifOp.props.animation == 'GEOM_NIF':
                # for morrowind: everything except keyframe controllers
                NifLog.info("Exporting geometry only")

            # find nif version to write

            self.version, data = scene.get_version_data()
            NifData.init(data)

            # export the actual root node (the name is fixed later to avoid confusing the exporter with duplicate names)
            root_block = self.objecthelper.export_root_node(self.root_objects, filebase)

            # post-processing:
            # ----------------

            NifLog.info("Checking controllers")
            if bpy.context.scene.niftools_scene.game == 'MORROWIND':
                # animations without keyframe animations crash the TESCS
                # if we are in that situation, add a trivial keyframe animation
                has_keyframecontrollers = False
                for block in block_store.block_to_obj:
                    if isinstance(block, NifFormat.NiKeyframeController):
                        has_keyframecontrollers = True
                        break
                if (not has_keyframecontrollers) and (not NifOp.props.bs_animation_node):
                    NifLog.info("Defining dummy keyframe controller")
                    # add a trivial keyframe controller on the scene root
                    self.transform_anim.create_controller(root_block, root_block.name)

                if NifOp.props.bs_animation_node:
                    for block in block_store.block_to_obj:
                        if isinstance(block, NifFormat.NiNode):
                            # if any of the shape children has a controller or if the ninode has a controller convert its type
                            if block.controller or any(child.controller for child in block.children if isinstance(child, NifFormat.NiGeometry)):
                                new_block = NifFormat.NiBSAnimationNode().deepcopy(block)
                                # have to change flags to 42 to make it work
                                new_block.flags = 42
                                root_block.replace_global_node(block, new_block)
                                if root_block is block:
                                    root_block = new_block

            # oblivion skeleton export: check that all bones have a transform controller and transform interpolator
            if bpy.context.scene.niftools_scene.game in ('OBLIVION', 'FALLOUT_3', 'SKYRIM') and filebase.lower() in ('skeleton', 'skeletonbeast'):
                self.transform_anim.add_dummy_controllers()

            # bhkConvexVerticesShape of children of bhkListShapes need an extra bhkConvexTransformShape (see issue #3308638, reported by Koniption)
            # note: block_store.block_to_obj changes during iteration, so need list copy
            for block in list(block_store.block_to_obj.keys()):
                if isinstance(block, NifFormat.bhkListShape):
                    for i, sub_shape in enumerate(block.sub_shapes):
                        if isinstance(sub_shape, NifFormat.bhkConvexVerticesShape):
                            coltf = block_store.create_block("bhkConvexTransformShape")
                            coltf.material = sub_shape.material
                            coltf.unknown_float_1 = 0.1
                            unk_8 = coltf.unknown_8_bytes
                            unk_8[0] = 96
                            unk_8[1] = 120
                            unk_8[2] = 53
                            unk_8[3] = 19
                            unk_8[4] = 24
                            unk_8[5] = 9
                            unk_8[6] = 253
                            unk_8[7] = 4
                            coltf.transform.set_identity()
                            coltf.shape = sub_shape
                            block.sub_shapes[i] = coltf

            # export constraints
            for b_obj in self.exportable_objects:
                if b_obj.constraints:
                    self.constrainthelper.export_constraints(b_obj, root_block)

            object_prop = ObjectProperty()
            object_prop.export_root_node_properties(root_block)

            # FIXME:
            """
            if self.EXPORT_FLATTENSKIN:
                # (warning: trouble if armatures parent other armatures or
                # if bones parent geometries, or if object is animated)
                # flatten skins
                skelroots = set()
                affectedbones = []
                for block in block_store.block_to_obj:
                    if isinstance(block, NifFormat.NiGeometry) and block.is_skin():
                        NifLog.info("Flattening skin on geometry {0}".format(block.name))
                        affectedbones.extend(block.flatten_skin())
                        skelroots.add(block.skin_instance.skeleton_root)
                # remove NiNodes that do not affect skin
                for skelroot in skelroots:
                    NifLog.info("Removing unused NiNodes in '{0}'".format(skelroot.name))
                    skelrootchildren = [child for child in skelroot.children
                                        if ((not isinstance(child,
                                                            NifFormat.NiNode))
                                            or (child in affectedbones))]
                    skelroot.num_children = len(skelrootchildren)
                    skelroot.children.update_size()
                    for i, child in enumerate(skelrootchildren):
                        skelroot.children[i] = child
            """

            # apply scale
            data.roots = [root_block]
            scale_correction = bpy.context.scene.niftools_scene.scale_correction
            if abs(scale_correction) > NifOp.props.epsilon:
                self.apply_scale(data, round(1 / NifOp.props.scale_correction))
                # also scale egm
                if EGMData.data:
                    EGMData.data.apply_scale(1 / scale_correction)

            # generate mopps (must be done after applying scale!)
            if bpy.context.scene.niftools_scene.game in ('OBLIVION', 'FALLOUT_3', 'SKYRIM'):
                for block in block_store.block_to_obj:
                    if isinstance(block, NifFormat.bhkMoppBvTreeShape):
                        NifLog.info("Generating mopp...")
                        block.update_mopp()
                        # print "=== DEBUG: MOPP TREE ==="
                        # block.parse_mopp(verbose = True)
                        # print "=== END OF MOPP TREE ==="
                        # warn about mopps on non-static objects
                        if any(sub_shape.layer != 1 for sub_shape in block.shape.sub_shapes):
                            NifLog.warn("Mopps for non-static objects may not function correctly in-game. You may wish to use simple primitives for collision.")

            # export nif file:
            # ----------------
            if bpy.context.scene.niftools_scene.game == 'EMPIRE_EARTH_II':
                ext = ".nifcache"
            else:
                ext = ".nif"

            # make sure we have the right file extension
            if fileext.lower() != ext:
                NifLog.warn(f"Changing extension from {fileext} to {ext} on output file")
            niffile = os.path.join(directory, prefix + filebase + ext)

            data.roots = [root_block]
            # todo [export] I believe this is redundant and setting modification only is the current way?
            data.neosteam = (bpy.context.scene.niftools_scene.game == 'NEOSTEAM')
            if bpy.context.scene.niftools_scene.game == 'NEOSTEAM':
                data.modification = "neosteam"
            elif bpy.context.scene.niftools_scene.game == 'ATLANTICA':
                data.modification = "ndoors"
            elif bpy.context.scene.niftools_scene.game == 'HOWLING_SWORD':
                data.modification = "jmihs1"

            NifLog.info(f"Writing .nif file: {niffile}")
            with open(niffile, "wb") as stream:
                data.write(stream)

            if NifOp.props.export_nft:
                nftfile = os.path.join(directory, prefix + filebase + ".nft")
                NifLog.info(f"Writing .nft file: {nftfile}")
                embedded_data = self._create_embedded_texture_data(data, root_block)
                
                with open(nftfile, "wb") as stream:
                    embedded_data.write(stream)

            # export egm file:
            # -----------------
            if EGMData.data:
                ext = ".egm"
                egmfile = os.path.join(directory, filebase + ext)
                NifLog.info(f"Writing {ext} file: {egmfile}")

                with open(egmfile, "wb") as stream:
                    EGMData.data.write(stream)

            # save exported file (this is used by the test suite)
            self.root_blocks = [root_block]
            NifLog.info("Finished")

        except NifError:
            return {'CANCELLED'}

        return {'FINISHED'}

    def _create_embedded_texture_data(self, data, root_block):
        NifLog.info(f"[NFT] Creating texture container from {root_block.__class__.__name__}")
        embedded_data = NifFormat.Data()
        embedded_data.version = data.version
        embedded_data.modification = data.modification
        embedded_data.neosteam = data.neosteam
        
        nft_roots = []
        found_count = 0
        embedded_count = 0
        
        # In a .nft file, the root blocks are only the NiSourceTexture blocks.
        # There is no geometry data. We extract them from the original tree.
        for source_texture in root_block.tree(block_type=NifFormat.NiSourceTexture):
            found_count += 1
            file_name = source_texture.file_name
            orig_file_name = file_name
            
            if not source_texture.use_external:
                continue
                
            if isinstance(file_name, bytes):
                file_name = file_name.decode('utf-8', 'ignore')
            if not file_name:
                continue
                
            image = self._load_texture_image(file_name)
            if image is None:
                NifLog.warn(f"[NFT] Could not load texture '{file_name}'")
                continue
                
            # Create a completely new root NiSourceTexture block for the .nft file
            nft_tex = NifFormat.NiSourceTexture()
            nft_tex.use_external = 0
            nft_tex.unknown_byte = 1
            
            # Use the absolute path of the Blender image for embedding
            try:
                abs_path = os.path.normpath(bpy.path.abspath(image.filepath))
            except Exception:
                abs_path = image.name
                
            nft_tex.file_name = abs_path.encode('utf-8')
                
            if hasattr(nft_tex, 'pixel_layout'):
                nft_tex.pixel_layout = 6 # PIX_LAY_DEFAULT or appropriate enum
            if hasattr(nft_tex, 'use_mipmaps'):
                nft_tex.use_mipmaps = 0 # MIP_FMT_NO
            if hasattr(nft_tex, 'alpha_format'):
                nft_tex.alpha_format = 0 # ALPHA_DEFAULT
            if hasattr(nft_tex, 'is_static'):
                nft_tex.is_static = 1
            if hasattr(nft_tex, 'direct_render'):
                nft_tex.direct_render = False
            if hasattr(nft_tex, 'persist_render_data'):
                nft_tex.persist_render_data = False
                
            # Add Extra Data and PixelData blocks to the NiSourceTexture
            str_extra = NifFormat.NiStringExtraData()
            str_extra.name = b""
            str_extra.bytes_data = nft_tex.file_name
            
            int_extra = NifFormat.NiIntegerExtraData()
            int_extra.name = b"NifPackMinorVersion"
            int_extra.integer_data = 2
            
            nft_tex.num_extra_data_list = 2
            nft_tex.extra_data_list.update_size()
            nft_tex.extra_data_list[0] = str_extra
            nft_tex.extra_data_list[1] = int_extra
            
            # Create and attach the core PixelData
            pixel_data_block = self._create_pixeldata_from_image(image)
            nft_tex.pixel_data = pixel_data_block
            
            nft_roots.append(nft_tex)
            embedded_count += 1
            NifLog.info(f"[NFT] Added root NiSourceTexture for '{file_name}'")
            
        embedded_data.roots = nft_roots
        NifLog.info(f"[NFT] NFT generation complete: found {found_count} textures, packed {embedded_count} as root blocks.")
        return embedded_data

    @staticmethod
    def _resolve_texture_path(file_name):
        normalized = file_name.replace('\\', os.sep).replace('/', os.sep)
        if os.path.isabs(normalized):
            path = normalized
        elif normalized.startswith('//'):
            path = bpy.path.abspath(normalized)
        else:
            path = os.path.join(os.path.dirname(NifOp.props.filepath), normalized)
            if not os.path.exists(path):
                path = os.path.abspath(normalized)

        if os.path.exists(path):
            return os.path.normpath(path)

        base_name = os.path.basename(normalized)
        name, ext = os.path.splitext(base_name)
        candidate_exts = [ext] if ext else []
        candidate_exts.extend(['.tga', '.dds', '.png', '.jpg', '.jpeg', '.bmp'])

        search_dirs = [
            os.path.dirname(path),
            os.path.dirname(NifOp.props.filepath),
        ]
        if normalized.startswith('//'):
            search_dirs.append(os.path.dirname(bpy.path.abspath(normalized)))

        seen = set()
        for search_dir in search_dirs:
            if not search_dir:
                continue
            search_dir = os.path.normpath(search_dir)
            if search_dir in seen:
                continue
            seen.add(search_dir)
            for candidate_ext in candidate_exts:
                candidate = os.path.join(search_dir, name + candidate_ext)
                if os.path.exists(candidate):
                    return os.path.normpath(candidate)

        return os.path.normpath(path)

    def _load_texture_image(self, file_name):
        search_name = os.path.splitext(os.path.basename(file_name))[0].lower()
        NifLog.info(f"[NFT] Looking for image matching '{search_name}' in exported objects")

        for b_obj in self.exportable_objects:
            if b_obj.type != 'MESH':
                continue

            for mat in b_obj.data.materials:
                if not mat or not getattr(mat, "use_nodes", False):
                    continue

                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE' and node.image:
                        image = node.image

                        img_path_name = os.path.splitext(os.path.basename(image.filepath))[0].lower()
                        img_obj_name = os.path.splitext(image.name)[0].lower()

                        if img_path_name == search_name or img_obj_name == search_name:
                            if not getattr(image, "has_data", False):
                                NifLog.warn(f"[NFT] Texture '{image.name}' has no pixel data in Blender. Skipping packing.")
                                return None
                            if getattr(image, "source", None) == 'GENERATED' and image.size[0] == 1 and image.size[1] == 1:
                                NifLog.warn(f"[NFT] Texture '{image.name}' is a 1x1 generated dummy image. Skipping packing.")
                                return None
                            try:
                                abs_path = os.path.normpath(bpy.path.abspath(image.filepath))
                                if not getattr(image, "packed_file", None) and not os.path.exists(abs_path):
                                    NifLog.warn(f"[NFT] Texture '{image.name}' physical file is missing from PC path '{abs_path}'. Skipping packing.")
                                    return None
                            except Exception:
                                pass

                            NifLog.info(f"[NFT] Found used image from mesh material: {image.name}")
                            return image

        NifLog.warn(f"[NFT] Could not find the original image for '{file_name}' assigned in exported materials!")
        return None

    @staticmethod
    def _create_pixeldata_from_image(image):
        width, height = image.size
        pixels = list(image.pixels)
        num_pixels = width * height
        num_bytes = num_pixels * 4
        
        NifLog.info(f"[NFT] Preparing pixel data for {image.name} ({width}x{height})")
        
        if not any(pixels):
            NifLog.warn(f"[NFT] WARNING: The loaded image {image.name} has all empty/zero pixels!")

        pixeldata = NifFormat.NiPixelData()
        pixeldata.num_pixels = num_pixels
        pixeldata.num_faces = 1
        pixeldata.num_mipmaps = 1
        pixeldata.bytes_per_pixel = 4
        pixeldata.bits_per_pixel = 32
        
        if hasattr(pixeldata, 'pixel_format'):
            pixeldata.pixel_format = 1 
            
        pixeldata.red_mask = 0x000000FF
        pixeldata.green_mask = 0x0000FF00
        pixeldata.blue_mask = 0x00FF0000
        pixeldata.alpha_mask = 0xFF000000
        
        if hasattr(pixeldata, "bits_per_pixel"):
            pixeldata.bits_per_pixel = 32
            
        if hasattr(pixeldata, "unknown_int_2"):
            pixeldata.unknown_int_2 = -1
            
        if hasattr(pixeldata, "flags"):
            pixeldata.flags = 1
            
        if hasattr(pixeldata, "channels"):
            pixeldata.channels.update_size()
            for i, c in enumerate(pixeldata.channels):
                c.type = i  # 0=Red, 1=Green, 2=Blue, 3=Alpha/Empty
                c.convention = 0
                c.bits_per_channel = 8
        
        if hasattr(pixeldata, "unknown_8_bytes"):
            pixeldata.unknown_8_bytes.update_size()
            for i, b in enumerate((129, 8, 130, 32, 0, 65, 12, 0)):
                if i < len(pixeldata.unknown_8_bytes):
                    pixeldata.unknown_8_bytes[i] = b
                    
        pixeldata.mipmaps.update_size()
        pixeldata.mipmaps[0].width = width
        pixeldata.mipmaps[0].height = height
        pixeldata.mipmaps[0].offset = 0

        # The pixel data is stored in a single byte array. The length of this array is num_pixels * bytes_per_pixel.
        pixeldata.num_pixels = num_bytes
        pixeldata.pixel_data.update_size()
        
        byte_data = bytearray(num_bytes)
        for y in range(height):
            for x in range(width):
                src_i = ((height - 1 - y) * width + x) * 4
                dst_i = (y * width + x) * 4
                # Convert from Blender's float RGBA to byte RGBA, clamping values to [0,1] and scaling to [0,255]
                byte_data[dst_i]   = int(max(0.0, min(1.0, pixels[src_i])) * 255.0)
                byte_data[dst_i+1] = int(max(0.0, min(1.0, pixels[src_i+1])) * 255.0)
                byte_data[dst_i+2] = int(max(0.0, min(1.0, pixels[src_i+2])) * 255.0)
                byte_data[dst_i+3] = int(max(0.0, min(1.0, pixels[src_i+3])) * 255.0)
            
        NifLog.info(f"[NFT] Assigning PyFFI pixel data elements...")
        
        data_row = pixeldata.pixel_data[0]
        
        # if it has _items, we can assign the whole bytearray at once, otherwise we have to assign byte by byte
        if hasattr(data_row, "_items"):
            data_row._items = list(byte_data)
        else:
            for i in range(num_bytes):
                data_row[i] = byte_data[i]
        
        return pixeldata
