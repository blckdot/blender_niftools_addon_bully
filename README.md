# blender_niftools_addon_bully

This is a modified fork of a VicLourenco modified fork that's essentially a fork of the official NifTools Blender Addon for importing and exporting .nif files, specifically optimized for Bully: Scholarship Edition. If you like forks, please make a fork, we need more forks! I personally like pitchforks more.

## Compatibility
Compatible with Blender 5.x, may NOT be compatible with anything lower than that. For Blender 2.8 - 3.6, you can use original VicLourenco modified fork that can be found in **[Bully Modding Discord](https://discord.gg/RcCAE8csCP)**

## Features of original VicLourenco modified fork:
- On import, Bully is now prioritized above other potential originating games
- Similar materials are no longer merged
- Vertex colors are exported properly
- Tangents and Bitangents are exported properly
- NiTexturingProperty nodes have their properties fixed

## Screenshots
<details>
<summary>Click to expand screenshots</summary>
  
![20260401131135_1](https://github.com/user-attachments/assets/4cd37934-2b36-422f-9663-8156e2c6216a)
![20260403211727_1](https://github.com/user-attachments/assets/aec979e5-8436-4b2d-99a6-78fd4a194a21)
![20260411230233_1](https://github.com/user-attachments/assets/31e9e1a7-9bd5-4379-aec9-dad4eb458789)
![20260411234445_1](https://github.com/user-attachments/assets/57dc1878-acf1-4000-a10d-35cc6ff1bcc3)
![20260412000149_1](https://github.com/user-attachments/assets/2010f2c1-1427-4144-b650-31a530dc93f9)
![20260413195334_1](https://github.com/user-attachments/assets/a9ca24ed-1064-4e8e-8e60-af304b468313)
![20260421100809_1](https://github.com/user-attachments/assets/bb6b3708-72ab-4b58-9f69-cd9bbba695c9)


</details>

## Installation
1. Download the repository as a `.zip` file.
2. In Blender 5.x, go to `Edit > Preferences > Get Extensions`.
3. Click the drop-down arrow in the top right and select `Install from Disk...`.
4. Select the `.zip` file and enable the addon.

## Editing Your Model
1. Import the .nif to be rigged over with the addon's default settings, make your changes, rig your model, whatever it is you want to do until you're ready for export.

## Preparing Your Model for Export
1. In Object Properties, make sure the model's Location, Rotation and Scale are 0, 0 and 1, respectively. If they're not, while in Object Mode, select your model, Object>Apply>All Transforms.

2. In Object Data Properties: Make sure your UV Map is called "UV0".
In Color Attributes, make sure yours is called "RGBA". If you don't already have one, set Domain to Face Corner, Data Type to Byte Color, and Color to "BCBCBC" (Hex)

3. In Material Properties, make sure your model is using a BULLY material. Just use any that came with the .nif you're trying to replace. (E.g., all Torso clothes for Jimmy will come with the "brownjacket_MS" material)

## Exporting Your Model
1. In the export menu, make sure to turn off "Force DDS" and "Optimise Materials", then export.

2. Open the exported .nif in **[NifSkope](https://github.com/niftools/nifskope/releases/tag/nifskope-1.1.3)**, expand your model's NiTriShape>NiTexturingProperty, in Block Details at the bottom, find Base Texture and set "Flags" to 12800. Not doing this will make the game crash, and needs to be done for every mesh of your model using a different material. You're done, load the model in-game and test your changes.

## Additional Notes
- Rigged clothes/peds have certain bones which don't need vertex groups, but Blender will generate them when you attach your model to their armature. Use the original .nif as a reference to check which groups you can delete. (E.g., gameplay clothes models for Jimmy don't need "Root" and "Root01", so those can safely be deleted)

- Jimmy's clothes refuse to load any more than 1 texture when in-game. As such, make sure your whole model uses a single material.

- Do not use multiple materials for a single mesh.

- Most models in the game have backface culling turned on. To disable it, open your exported .nif, expand your model's NiTriShape>Add a "NiStencilProperty" if you don't have it, and in Block Details at the bottom, scroll all the way down and set "Flags" to 19840.

## Credits
* **VicLourenco** for the initial optimizations for Bully: Scholarship Edition.
* The amazing **[NifTools Team](https://github.com/niftools/blender_niftools_addon)** who originally created and maintained the core architecture. 
* **SimonBestia** for the guide on how to mod the game models/additional information and overall contribution to the Bully community.

## Bugs and Issues
If you will come across any bugs, do not create an issue, just make another fork!
