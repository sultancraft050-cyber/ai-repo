/*
CPU <-> Motherboard socket validation.
*/
MATCH (cpu:CPU {id: $cpu_id})
MATCH (board:Motherboard {id: $motherboard_id})
OPTIONAL MATCH (cpu)-[:REQUIRES_SOCKET]->(socket:Socket)<-[:HAS_SOCKET]-(board)
RETURN socket IS NOT NULL AS compatible,
       socket.name AS socket,
       cpu.name AS cpu_name,
       board.name AS motherboard_name;

/*
PCIe lane validation for a selected configuration.
Device IDs should include PCIe consumers such as GPU and NVMe storage.
*/
MATCH (cpu:CPU {id: $cpu_id})
MATCH (board:Motherboard {id: $motherboard_id})
WITH cpu,
     board,
     coalesce(cpu.bandwidth_pcie_lanes, 0) AS cpu_lanes,
     coalesce(board.bandwidth_chipset_pcie_lanes, 0) AS chipset_lanes,
     coalesce(cpu.bandwidth_pcie_generation, 0) AS cpu_gen,
     coalesce(board.bandwidth_pcie_generation, 0) AS board_gen
UNWIND $device_ids AS device_id
MATCH (device {id: device_id})
WITH cpu_lanes,
     chipset_lanes,
     cpu_gen,
     board_gen,
     collect({
       id: device.id,
       lanes: coalesce(device.bandwidth_pcie_lanes_required, 0),
       generation: coalesce(device.bandwidth_pcie_generation_required, 0)
     }) AS consumers
WITH cpu_lanes,
     chipset_lanes,
     cpu_gen,
     board_gen,
     consumers,
     reduce(total = 0, consumer IN consumers | total + consumer.lanes) AS requested_lanes,
     reduce(max_gen = 0, consumer IN consumers |
       CASE WHEN consumer.generation > max_gen THEN consumer.generation ELSE max_gen END
     ) AS requested_generation
RETURN requested_lanes <= cpu_lanes + chipset_lanes AS lane_budget_valid,
       requested_generation <= CASE WHEN cpu_gen < board_gen THEN cpu_gen ELSE board_gen END AS generation_valid,
       requested_lanes,
       cpu_lanes,
       chipset_lanes,
       requested_generation,
       cpu_gen,
       board_gen,
       consumers;

/*
USB front-panel topology validation.
*/
MATCH (board:Motherboard {id: $motherboard_id})
MATCH (chassis:Case {id: $case_id})
WITH board,
     chassis,
     coalesce(chassis.bandwidth_front_usb_20_ports, 0) AS required_usb2,
     coalesce(chassis.bandwidth_front_usb_32_gen1_ports, 0) AS required_gen1,
     coalesce(chassis.bandwidth_front_usb_32_gen2x2_ports, 0) AS required_gen2x2,
     coalesce(board.bandwidth_usb_20_headers, 0) AS usb2_headers,
     coalesce(board.bandwidth_usb_32_gen1_headers, 0) AS gen1_headers,
     coalesce(board.bandwidth_usb_32_gen2x2_headers, 0) AS gen2x2_headers,
     coalesce(board.bandwidth_usb_controller_gbps, 0) AS controller_gbps
WITH *,
     required_usb2 * 0.48 + required_gen1 * 5 + required_gen2x2 * 20 AS requested_gbps
RETURN required_usb2 <= usb2_headers
       AND required_gen1 <= gen1_headers
       AND required_gen2x2 <= gen2x2_headers AS header_valid,
       requested_gbps <= controller_gbps AS bandwidth_valid,
       requested_gbps,
       controller_gbps,
       {
         required_usb2: required_usb2,
         required_gen1: required_gen1,
         required_gen2x2: required_gen2x2,
         usb2_headers: usb2_headers,
         gen1_headers: gen1_headers,
         gen2x2_headers: gen2x2_headers
       } AS topology;

/*
3D volumetric collision query using axis-aligned bounding boxes.
Python repeats this calculation after Neo4j returns component dimensions so validation
does not depend on a single layer.
*/
MATCH (a:Component)
MATCH (b:Component)
WHERE a.id IN $component_ids
  AND b.id IN $component_ids
  AND a.id < b.id
  AND a.dim_volume_width_mm IS NOT NULL
  AND b.dim_volume_width_mm IS NOT NULL
WITH a,
     b,
     coalesce(a.dim_volume_x_mm, 0) AS ax,
     coalesce(a.dim_volume_y_mm, 0) AS ay,
     coalesce(a.dim_volume_z_mm, 0) AS az,
     a.dim_volume_width_mm AS aw,
     a.dim_volume_height_mm AS ah,
     a.dim_volume_depth_mm AS ad,
     coalesce(b.dim_volume_x_mm, 0) AS bx,
     coalesce(b.dim_volume_y_mm, 0) AS by,
     coalesce(b.dim_volume_z_mm, 0) AS bz,
     b.dim_volume_width_mm AS bw,
     b.dim_volume_height_mm AS bh,
     b.dim_volume_depth_mm AS bd
WITH a,
     b,
     ax < bx + bw AND ax + aw > bx
     AND ay < by + bh AND ay + ah > by
     AND az < bz + bd AND az + ad > bz AS collision
RETURN a.id AS source_id,
       b.id AS target_id,
       collision
ORDER BY collision DESC, source_id, target_id;

