CREATE CONSTRAINT cpu_id IF NOT EXISTS FOR (n:CPU) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT gpu_id IF NOT EXISTS FOR (n:GPU) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT motherboard_id IF NOT EXISTS FOR (n:Motherboard) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT ram_id IF NOT EXISTS FOR (n:RAM) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT case_id IF NOT EXISTS FOR (n:Case) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT cooler_id IF NOT EXISTS FOR (n:Cooler) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT storage_id IF NOT EXISTS FOR (n:Storage) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT psu_id IF NOT EXISTS FOR (n:PSU) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT socket_name IF NOT EXISTS FOR (n:Socket) REQUIRE n.name IS UNIQUE;
CREATE CONSTRAINT memory_type_name IF NOT EXISTS FOR (n:MemoryType) REQUIRE n.name IS UNIQUE;
CREATE INDEX component_brand IF NOT EXISTS FOR (n:Component) ON (n.brand);
CREATE INDEX component_price IF NOT EXISTS FOR (n:Component) ON (n.price_usd);
CREATE INDEX motherboard_form_factor IF NOT EXISTS FOR (n:Motherboard) ON (n.spec_form_factor);
CREATE CONSTRAINT product_canonical_key IF NOT EXISTS FOR (n:Product) REQUIRE n.canonical_key IS UNIQUE;
CREATE CONSTRAINT vendor_id IF NOT EXISTS FOR (n:Vendor) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT price_snapshot_id IF NOT EXISTS FOR (n:PriceSnapshot) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT pricing_job_id IF NOT EXISTS FOR (n:PricingJob) REQUIRE n.id IS UNIQUE;
CREATE INDEX product_name IF NOT EXISTS FOR (n:Product) ON (n.name);
CREATE INDEX product_category IF NOT EXISTS FOR (n:Product) ON (n.category);
CREATE INDEX price_snapshot_timestamp IF NOT EXISTS FOR (n:PriceSnapshot) ON (n.timestamp);
CREATE INDEX price_snapshot_vendor IF NOT EXISTS FOR (n:PriceSnapshot) ON (n.vendor_id);

/*
Required graph shape. Runtime catalog data belongs in Neo4j, not in local JSON files.

(:CPU:Component {
  id, name, brand, price_usd,
  spec_core_count, spec_single_thread_score, spec_multi_thread_score,
  bandwidth_pcie_lanes, bandwidth_pcie_generation,
  power_tdp_w
})-[:REQUIRES_SOCKET]->(:Socket)

(:Motherboard:Component {
  id, name, brand, price_usd,
  spec_form_factor, spec_supported_form_factors,
  spec_memory_slots, spec_max_memory_mt_s,
  bandwidth_chipset_pcie_lanes, bandwidth_pcie_generation,
  bandwidth_usb_controller_gbps,
  bandwidth_usb_20_headers, bandwidth_usb_32_gen1_headers, bandwidth_usb_32_gen2x2_headers
})-[:HAS_SOCKET]->(:Socket)
  -[:SUPPORTS_MEMORY_TYPE]->(:MemoryType)

(:RAM:Component {
  id, name, brand, price_usd,
  spec_capacity_gb, spec_modules, spec_speed_mt_s,
  bandwidth_memory_gbps,
  dim_height_mm
})-[:USES_MEMORY_TYPE]->(:MemoryType)
  -[:QVL_VALIDATED_ON {max_stable_mt_s}]->(:Motherboard)

(:GPU:Component {
  id, name, brand, price_usd,
  spec_raster_score, spec_compute_score, spec_vram_gb,
  bandwidth_pcie_lanes_required, bandwidth_pcie_generation_required,
  power_board_power_w,
  dim_length_mm, dim_width_mm, dim_height_mm,
  dim_volume_x_mm, dim_volume_y_mm, dim_volume_z_mm,
  dim_volume_width_mm, dim_volume_height_mm, dim_volume_depth_mm
})

(:Case:Component {
  id, name, brand, price_usd,
  spec_supported_form_factors,
  dim_gpu_clearance_mm, dim_cooler_clearance_mm,
  bandwidth_front_usb_20_ports, bandwidth_front_usb_32_gen1_ports,
  bandwidth_front_usb_32_gen2x2_ports
})

(:Cooler:Component {
  id, name, brand, price_usd,
  spec_cooling_capacity_w,
  power_fan_power_w,
  dim_height_mm,
  dim_volume_x_mm, dim_volume_y_mm, dim_volume_z_mm,
  dim_volume_width_mm, dim_volume_height_mm, dim_volume_depth_mm
})-[:SUPPORTS_SOCKET]->(:Socket)

(:Storage:Component {
  id, name, brand, price_usd,
  spec_capacity_gb,
  bandwidth_pcie_lanes_required,
  bandwidth_pcie_generation_required,
  power_peak_w
})

(:PSU:Component {
  id, name, brand, price_usd,
  spec_continuous_wattage,
  spec_efficiency_rating,
  power_12v_w
})

Relationships used by the solver:
(:Component)-[:COMPATIBLE_WITH]->(:Component)
(:GPU)-[:FITS_IN_CASE]->(:Case)
(:Component)-[:USES_PCIe_LANES {lanes, generation, source}]->(:Motherboard)
(:Component)-[:SHARES_BANDWIDTH {controller, gbps}]->(:Motherboard)
(:Component)-[:BLOCKS_PHYSICAL_SPACE {reason}]->(:Component)

Pricing intelligence graph:
(:Product {
  id, canonical_key, name, brand, category, model, normalized_model,
  msrp, imageUrl,
  current_best_price, current_best_currency, current_best_vendor,
  current_price_timestamp, current_price_freshness_score,
  current_price_trust_score, current_price_source,
  stale, stale_reason
})

(:Vendor {
  id, name, region, apiType, trust_score
})

(:PriceSnapshot {
  id, price, currency, availability, timestamp, shipping_cost,
  product_url, source_product_id, seller, condition, rating,
  source, source_type, source_tier, trust_score, freshness_score,
  accepted, stale, flags
})

(:FieldEvidence {
  id, field, value_json, source, timestamp,
  trust_score, freshness_score, source_tier
})

(:Product)-[:SOLD_BY]->(:Vendor)
(:Product)-[:HAS_PRICE]->(:PriceSnapshot)
(:PriceSnapshot)-[:FROM_VENDOR]->(:Vendor)
(:Product)-[:HAS_FIELD_EVIDENCE]->(:FieldEvidence)

Compatibility component nodes may also carry the Product label. When a trusted
PriceSnapshot is accepted, the Product current-price view updates and USD prices
also update component.price_usd so the auto-build solver optimizes with the
freshest accepted market data.
*/
