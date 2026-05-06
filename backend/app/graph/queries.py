CPU_MOTHERBOARD_SOCKET = """
MATCH (cpu:CPU {id: $cpu_id})
MATCH (board:Motherboard {id: $motherboard_id})
OPTIONAL MATCH (cpu)-[:REQUIRES_SOCKET]->(socket:Socket)<-[:HAS_SOCKET]-(board)
RETURN socket IS NOT NULL AS compatible,
       socket.name AS socket,
       cpu.name AS cpu_name,
       board.name AS motherboard_name
"""

RAM_MOTHERBOARD_QVL = """
MATCH (ram:RAM {id: $ram_id})
MATCH (board:Motherboard {id: $motherboard_id})
OPTIONAL MATCH (ram)-[:USES_MEMORY_TYPE]->(memory:MemoryType)<-[:SUPPORTS_MEMORY_TYPE]-(board)
OPTIONAL MATCH (ram)-[qvl:QVL_VALIDATED_ON]->(board)
RETURN memory IS NOT NULL AS memory_type_supported,
       memory.name AS memory_type,
       qvl IS NOT NULL AS qvl_validated,
       qvl.max_stable_mt_s AS qvl_max_stable_mt_s
"""

COOLER_SOCKET_SUPPORT = """
MATCH (cooler:Cooler {id: $cooler_id})
MATCH (cpu:CPU {id: $cpu_id})-[:REQUIRES_SOCKET]->(socket:Socket)
OPTIONAL MATCH (cooler)-[:SUPPORTS_SOCKET]->(socket)
RETURN socket.name AS socket,
       count(socket) > 0 AS supported
"""

KNOWN_SPACE_BLOCKERS = """
MATCH (a)-[r:BLOCKS_PHYSICAL_SPACE]->(b)
WHERE a.id IN $component_ids AND b.id IN $component_ids
RETURN DISTINCT a.id AS source_id,
       b.id AS target_id,
       coalesce(r.reason, "known physical interference") AS reason
"""

RELATIONSHIPS_BETWEEN_SELECTED = """
MATCH (source)-[relationship]->(target)
WHERE source.id IN $component_ids AND target.id IN $component_ids
RETURN source.id AS source_id,
       type(relationship) AS relationship_type,
       target.id AS target_id,
       properties(relationship) AS properties
"""

COMPONENTS_BY_IDS = """
MATCH (component)
WHERE component.id IN $component_ids
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
"""

COMPONENT_OPTIONS = """
MATCH (component)
WHERE $kind IN labels(component)
  AND ($max_price IS NULL OR component.price_usd <= $max_price)
  AND (size($brand_bias) = 0 OR component.brand IN $brand_bias)
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
ORDER BY coalesce(component.price_usd, 999999), component.name
LIMIT $limit
"""

COMPONENTS_BY_KIND = """
MATCH (component)
WHERE $kind IN labels(component)
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
ORDER BY coalesce(component.price_usd, 999999), component.name
LIMIT $limit
"""

MOTHERBOARD_OPTIONS_FOR_CPU = """
MATCH (cpu:CPU {id: $cpu_id})-[:REQUIRES_SOCKET]->(:Socket)<-[:HAS_SOCKET]-(component:Motherboard)
WHERE ($form_factor IS NULL OR component.spec_form_factor = $form_factor)
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
ORDER BY coalesce(component.price_usd, 999999), component.name
LIMIT $limit
"""

RAM_OPTIONS_FOR_BOARD = """
MATCH (board:Motherboard {id: $motherboard_id})-[:SUPPORTS_MEMORY_TYPE]->(:MemoryType)<-[:USES_MEMORY_TYPE]-(component:RAM)
OPTIONAL MATCH (component)-[qvl:QVL_VALIDATED_ON]->(board)
WITH component, qvl
WHERE $qvl_required = false OR qvl IS NOT NULL
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
ORDER BY coalesce(component.price_usd, 999999), component.name
LIMIT $limit
"""

CASE_OPTIONS_FOR_BOARD_AND_GPU = """
MATCH (component:Case)
WHERE ($form_factor IS NULL OR component.spec_supported_form_factors CONTAINS $form_factor)
  AND ($gpu_length_mm IS NULL OR component.dim_gpu_clearance_mm >= $gpu_length_mm)
RETURN component.id AS id,
       labels(component) AS labels,
       properties(component) AS properties
ORDER BY coalesce(component.price_usd, 999999), component.name
LIMIT $limit
"""
