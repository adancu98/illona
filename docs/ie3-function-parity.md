# IE3 tool inventory

Illona exposes 66 pinned IE3 tools under the `illona_pro_` prefix. Together with 16 base tools and four Creold tools, the MCP catalog contains 86 tools.

The runtime adapter is self-contained in `illona_mcp/ie3_runtime`; Node.js 20+ is required. Upstream attribution and commit IDs are preserved in that folder and in [third-party notices](../THIRD_PARTY_NOTICES.md).

| Tool | Purpose |
| --- | --- |
| `illona_pro_get_document_info` | Get Document Info |
| `illona_pro_get_artboards` | Get Artboards |
| `illona_pro_get_layers` | Get Layers |
| `illona_pro_get_selection` | Get Selection |
| `illona_pro_list_text_frames` | List Text Frames |
| `illona_pro_get_text_frame_detail` | Get Text Frame Detail |
| `illona_pro_get_colors` | Get Colors |
| `illona_pro_get_path_items` | Get Path Items |
| `illona_pro_get_guidelines` | Get Guidelines |
| `illona_pro_get_groups` | Get Groups |
| `illona_pro_get_effects` | Get Effects |
| `illona_pro_get_images` | Get Images |
| `illona_pro_get_symbols` | Get Symbols |
| `illona_pro_get_document_structure` | Get Document Structure |
| `illona_pro_find_objects` | Find Objects |
| `illona_pro_check_contrast` | Check Contrast |
| `illona_pro_extract_design_tokens` | Extract Design Tokens |
| `illona_pro_export` | Export |
| `illona_pro_export_pdf` | Export PDF |
| `illona_pro_get_overprint_info` | Get Overprint Info |
| `illona_pro_get_separation_info` | Get Separation Info |
| `illona_pro_preflight_check` | Preflight Check |
| `illona_pro_check_text_consistency` | Check Text Consistency |
| `illona_pro_set_workflow` | Set Workflow |
| `illona_pro_set_illustrator_version` | Set Illustrator Version |
| `illona_pro_create_rectangle` | Create Rectangle |
| `illona_pro_create_ellipse` | Create Ellipse |
| `illona_pro_create_line` | Create Line |
| `illona_pro_create_text_frame` | Create Text Frame |
| `illona_pro_create_path` | Create Path |
| `illona_pro_modify_object` | Modify Object |
| `illona_pro_convert_to_outlines` | Convert to Outlines |
| `illona_pro_place_image` | Place Image |
| `illona_pro_import_svg_as_editable` | Import SVG as Editable |
| `illona_pro_resize_for_variation` | Resize for Variation |
| `illona_pro_align_objects` | Align Objects |
| `illona_pro_replace_color` | Replace Color |
| `illona_pro_manage_layers` | Manage Layers |
| `illona_pro_place_color_chips` | Place Color Chips |
| `illona_pro_place_style_guide` | Place Style Guide |
| `illona_pro_create_crop_marks` | Create Crop Marks (トンボ) |
| `illona_pro_create_document` | Create Document |
| `illona_pro_close_document` | Close Document |
| `illona_pro_save_document` | Save Document |
| `illona_pro_open_document` | Open Document |
| `illona_pro_group_objects` | Group Objects |
| `illona_pro_ungroup_objects` | Ungroup Objects |
| `illona_pro_duplicate_objects` | Duplicate Objects |
| `illona_pro_list_fonts` | List Fonts |
| `illona_pro_manage_artboards` | Manage Artboards |
| `illona_pro_set_z_order` | Set Z-Order |
| `illona_pro_move_to_layer` | Move to Layer |
| `illona_pro_delete_objects` | Delete Objects |
| `illona_pro_apply_graphic_style` | Apply Graphic Style |
| `illona_pro_list_graphic_styles` | List Graphic Styles |
| `illona_pro_manage_swatches` | Manage Swatches |
| `illona_pro_apply_text_style` | Apply Text Style |
| `illona_pro_list_text_styles` | List Text Styles |
| `illona_pro_create_gradient` | Create Gradient |
| `illona_pro_manage_linked_images` | Manage Linked Images |
| `illona_pro_undo` | Undo / Redo |
| `illona_pro_manage_datasets` | Manage Variables & Datasets |
| `illona_pro_place_symbol` | Place Symbol |
| `illona_pro_create_path_text` | Create Path Text |
| `illona_pro_select_objects` | Select Objects |
| `illona_pro_convert_coordinate` | Convert Coordinate |

All Pro geometry uses points. Default `artboard-web` coordinates start at the top-left with Y down. Native document coordinates have Y up. Read the tool schema before choosing a coordinate system.

Native operations require explicit document IDs, preserve UUID targeting and produce durable operation receipts. Tool availability does not certify every parameter combination or print compliance.
