# Fuselage

A fuselage is a loft through cross-sections. The sections are grouped in
**segments**; each segment is lofted on its own, from its first section to its
last. A segment needs at least two sections. Most numeric fields accept a
formula; see [Parametric Model](../user-guide/parametric-model.md).

Select the fuselage to edit it in the **Parameters** tab.

## General

| Parameter | Unit | Description |
|---|---|---|
| Name | — | Name of the component. |
| Type | — | Component type. Read-only. |

## Segments

The **Segments** table has one row per segment.

| Column | Description |
|---|---|
| Tag | Name of the segment. Double-click to edit. |
| Sections | Number of sections in the segment. Read-only. |
| Method | **Smooth** lofts a smooth surface through the sections. **Ruled** joins neighbouring sections with straight lines. |

The buttons under the table add a segment after the selected one, duplicate,
move up, move down, and delete the selected segment. A new segment has two
circular sections of 100 mm diameter at X = 0 and X = 100 mm. The last segment
cannot be deleted.

## Sections

Select a segment to list its sections. The **Sections** table shows each
section's number, **Profile** type, **X** position, and **Size**.

The buttons under the table open the 2D inspector, add a section after the
selected one, duplicate, move up, move down, and delete the selected section.
A new section is a 100 mm circle. It is placed halfway between its neighbours,
or 100 mm behind the last section, or 100 mm in front of the first section. A
segment keeps at least two sections. The selected section is highlighted in
the 3D Viewer.

The **Transform** section below the table places the selected section in the
fuselage frame. The profile lies in the section's YZ plane.

| Parameter | Unit | Description |
|---|---|---|
| Position X | mm | Station of the section along the fuselage. |
| Position Y, Z | mm | Center of the profile. Use Z to raise or lower the section. |
| Rotation X, Y, Z | ° | Rotation of the section plane about its center. |

## Section profiles

**Section Properties** sets the profile of the selected section. Pick the shape
in **Profile**. Changing the shape resets the section to that shape's default
size.

| Profile | Parameter | Unit | Description |
|---|---|---|---|
| Circle | Diameter | mm | Diameter of the circle. Default 100. |
| Ellipse | Width | mm | Width along Y. Default 100. |
| Ellipse | Height | mm | Height along Z. Default 100. |
| Rectangle | Width, Height | mm | Outer size. Default 100 × 100. |
| Rectangle | Corner radius | mm | Radius of the four corners. Default 0. |
| Trapezoid | Top width | mm | Width of the upper (+Z) edge. Default 80. |
| Trapezoid | Bottom width | mm | Width of the lower (−Z) edge. Default 100. |
| Trapezoid | Height | mm | Height along Z. Default 100. |
| Trapezoid | Corner radius | mm | Radius of the four corners. Default 0. |
| Triangle | Base width | mm | Width of the base. Default 100. |
| Triangle | Height | mm | Height along Z. Default 100. |
| Triangle | Orientation | — | **Up** puts the apex at the top, **Down** at the bottom. |
| Triangle | Corner radius | mm | Radius of the three corners. Default 0. |
| Polygon | Vertices | — | Number of vertices. Edit them in the vertex table. |

A polygon profile has a vertex table with **Y**, **Z**, and **Radius** (all in
mm) for each vertex. Radius rounds that corner. A polygon needs at least three
vertices; the default is a triangle with vertices at (−50, −50), (50, −50), and
(0, 50).

Dimensions must not be negative. Each corner radius is limited so that it fits
on the edges next to it.

## 2D section inspector

Click **Inspect & Edit 2D Section...**, or double-click a section, to open the
**Fuselage Section Inspector**. Use **Segment** and the arrow buttons to move
between sections. The inspector edits the same **Profile Definition** and
**Section Transform** values as the panel. For a polygon, drag a vertex on the
canvas to move it, or click an edge to insert a vertex.

**Section Properties & Engineering Metrics** shows the area, perimeter, width
and height, aspect ratio (W/H), centroid, and hydraulic diameter of the
section. **Display Options** shows the previous and next sections as ghosts,
dimension annotations, the centroid, the grid, and the 128 sample points.
Click **Apply** to keep your changes, **Save & Close** to keep them and close,
or **Cancel** to discard the changes made since the last **Apply**.

Every fuselage profile is sampled with 128 points around its outline.

## Default shape

The **Model** group of the toolbar creates each part with a starting shape.
A new part is selected after it is created. Its name gets a number, such as
**Fuselage 2**, when the name is already taken.

| Property | Value |
|---|---|
| Name | Fuselage |
| Attached to | Vehicle |
| Mass | 350 g |
| Segments | One segment, tag `main`, method Smooth |
| Sections | Three circles at X = 0, 140, and 600 mm, with diameters 25, 120, and 35 mm |
