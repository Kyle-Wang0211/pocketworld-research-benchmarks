struct Params {
    width: u32,
    height: u32,
    pixel_count: u32,
    depth_count: u32,
    source_count: u32,
    patch_n: u32,
    min_views: u32,
    exclusion_radius: u32,
    min_std_u8: f32,
    ncc_min: f32,
    depth_margin: f32,
    inverse_depth_first: f32,
    inverse_depth_step: f32,
    padding0: f32,
    padding1: f32,
    padding2: f32,
    inverse_k0: vec4<f32>,
    inverse_k1: vec4<f32>,
    inverse_k2: vec4<f32>,
};

@group(0) @binding(0) var<storage, read> gray_frames: array<f32>;
@group(0) @binding(1) var<storage, read> source_projections: array<vec4<f32>>;
@group(0) @binding(2) var<uniform> params: Params;
@group(0) @binding(3) var<storage, read_write> best_index_output: array<u32>;
@group(0) @binding(4) var<storage, read_write> best_score_output: array<f32>;
@group(0) @binding(5) var<storage, read_write> second_score_output: array<f32>;
@group(0) @binding(6) var<storage, read_write> views_output: array<u32>;
@group(0) @binding(7) var<storage, read_write> accepted_output: array<u32>;

fn read_constant(image_offset: u32, x: i32, y: i32) -> f32 {
    if (x < 0 || y < 0 || x >= i32(params.width) || y >= i32(params.height)) {
        return 0.0;
    }
    return gray_frames[image_offset + u32(y) * params.width + u32(x)];
}

fn sample_bilinear_constant(image_offset: u32, input_x: f32, input_y: f32) -> f32 {
    let x = round(input_x * 32.0) / 32.0;
    let y = round(input_y * 32.0) / 32.0;
    let x0 = i32(floor(x));
    let y0 = i32(floor(y));
    let x1 = x0 + 1;
    let y1 = y0 + 1;
    let wx = x - f32(x0);
    let wy = y - f32(y0);
    let top = mix(
        read_constant(image_offset, x0, y0),
        read_constant(image_offset, x1, y0), wx);
    let bottom = mix(
        read_constant(image_offset, x0, y1),
        read_constant(image_offset, x1, y1), wx);
    return mix(top, bottom, wy);
}

fn reflect101(coordinate: i32, length: i32) -> i32 {
    if (length <= 1) {
        return 0;
    }
    var value = coordinate;
    loop {
        if (value >= 0 && value < length) {
            break;
        }
        if (value < 0) {
            value = -value;
        } else {
            value = 2 * length - value - 2;
        }
    }
    return value;
}

fn reference_ray(x: f32, y: f32) -> vec3<f32> {
    let pixel = vec4<f32>(x, y, 1.0, 0.0);
    return vec3<f32>(
        dot(params.inverse_k0, pixel),
        dot(params.inverse_k1, pixel),
        dot(params.inverse_k2, pixel));
}

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) global_id: vec3<u32>) {
    let gid = global_id.x;
    if (gid >= params.pixel_count) {
        return;
    }
    if (params.patch_n == 0u || params.patch_n * params.patch_n > 25u ||
        params.depth_count > 64u || params.source_count > 8u ||
        params.min_views == 0u || params.min_views > params.source_count) {
        best_index_output[gid] = 0u;
        best_score_output[gid] = -2.0;
        second_score_output[gid] = -2.0;
        views_output[gid] = 0u;
        accepted_output[gid] = 0u;
        return;
    }

    let x = gid % params.width;
    let y = gid / params.width;
    let half_patch = i32(params.patch_n / 2u);
    var reference_patch: array<f32, 25>;
    var reference_sum = 0.0;
    var sample_index = 0u;
    for (var dy = -half_patch; dy <= half_patch; dy = dy + 1) {
        for (var dx = -half_patch; dx <= half_patch; dx = dx + 1) {
            let reflected_x = reflect101(i32(x) + dx, i32(params.width));
            let reflected_y = reflect101(i32(y) + dy, i32(params.height));
            let value = gray_frames[u32(reflected_y) * params.width + u32(reflected_x)];
            reference_patch[sample_index] = value;
            sample_index = sample_index + 1u;
            reference_sum = reference_sum + value;
        }
    }
    let area = f32(sample_index);
    let reference_mean = reference_sum / area;
    var reference_variance = 0.0;
    for (var index = 0u; index < sample_index; index = index + 1u) {
        let centered = reference_patch[index] - reference_mean;
        reference_variance = reference_variance + centered * centered;
    }
    if (sqrt(reference_variance / area) < params.min_std_u8) {
        best_index_output[gid] = 0u;
        best_score_output[gid] = -2.0;
        second_score_output[gid] = -2.0;
        views_output[gid] = 0u;
        accepted_output[gid] = 0u;
        return;
    }

    var costs: array<f32, 64>;
    var depth_views: array<u32, 64>;
    let center_margin = f32(half_patch + 1);
    for (var depth_index = 0u; depth_index < params.depth_count;
         depth_index = depth_index + 1u) {
        let inverse_depth = params.inverse_depth_first +
            f32(depth_index) * params.inverse_depth_step;
        let depth = 1.0 / inverse_depth;
        var top_scores: array<f32, 8>;
        for (var top_index = 0u; top_index < 8u; top_index = top_index + 1u) {
            top_scores[top_index] = -2.0;
        }
        var valid_count = 0u;
        for (var source = 0u; source < params.source_count; source = source + 1u) {
            let projection_base = source * 3u;
            let center_ray = reference_ray(f32(x), f32(y));
            let center = vec4<f32>(center_ray * depth, 1.0);
            let center_z = dot(source_projections[projection_base + 2u], center);
            if (center_z <= 0.05) {
                continue;
            }
            let center_x = dot(source_projections[projection_base], center) / center_z;
            let center_y = dot(source_projections[projection_base + 1u], center) / center_z;
            if (center_x < center_margin || center_x >= f32(params.width) - center_margin ||
                center_y < center_margin || center_y >= f32(params.height) - center_margin) {
                continue;
            }

            var source_patch: array<f32, 25>;
            var source_sum = 0.0;
            var patch_index = 0u;
            let source_offset = (source + 1u) * params.pixel_count;
            for (var dy = -half_patch; dy <= half_patch; dy = dy + 1) {
                for (var dx = -half_patch; dx <= half_patch; dx = dx + 1) {
                    let reflected_x = reflect101(i32(x) + dx, i32(params.width));
                    let reflected_y = reflect101(i32(y) + dy, i32(params.height));
                    let ray = reference_ray(f32(reflected_x), f32(reflected_y));
                    let point = vec4<f32>(ray * depth, 1.0);
                    let z = dot(source_projections[projection_base + 2u], point);
                    var denominator = 1.0;
                    if (z > 1.0e-12) {
                        denominator = z;
                    }
                    let projected_x = dot(source_projections[projection_base], point) / denominator;
                    let projected_y = dot(source_projections[projection_base + 1u], point) / denominator;
                    let value = sample_bilinear_constant(
                        source_offset, projected_x, projected_y);
                    source_patch[patch_index] = value;
                    patch_index = patch_index + 1u;
                    source_sum = source_sum + value;
                }
            }
            let source_mean = source_sum / area;
            var source_variance = 0.0;
            var covariance = 0.0;
            for (var index = 0u; index < sample_index; index = index + 1u) {
                let reference_centered = reference_patch[index] - reference_mean;
                let source_centered = source_patch[index] - source_mean;
                source_variance = source_variance + source_centered * source_centered;
                covariance = covariance + reference_centered * source_centered;
            }
            if (sqrt(source_variance / area) < params.min_std_u8) {
                continue;
            }
            let score = covariance /
                (sqrt(reference_variance * source_variance) + 1.0e-6);
            valid_count = valid_count + 1u;
            for (var slot = 0u; slot < params.min_views; slot = slot + 1u) {
                if (score <= top_scores[slot]) {
                    continue;
                }
                var shift = params.min_views - 1u;
                loop {
                    if (shift <= slot) {
                        break;
                    }
                    top_scores[shift] = top_scores[shift - 1u];
                    shift = shift - 1u;
                }
                top_scores[slot] = score;
                break;
            }
        }
        var cost = -2.0;
        if (valid_count >= params.min_views) {
            cost = 0.0;
            for (var index = 0u; index < params.min_views; index = index + 1u) {
                cost = cost + top_scores[index];
            }
            cost = cost / f32(params.min_views);
        }
        costs[depth_index] = cost;
        depth_views[depth_index] = valid_count;
    }

    var best_index = 0u;
    var best_score = costs[0];
    for (var index = 1u; index < params.depth_count; index = index + 1u) {
        if (costs[index] > best_score) {
            best_score = costs[index];
            best_index = index;
        }
    }
    var second_score = -2.0;
    for (var index = 0u; index < params.depth_count; index = index + 1u) {
        let delta = i32(index) - i32(best_index);
        if (abs(delta) <= i32(params.exclusion_radius)) {
            continue;
        }
        second_score = max(second_score, costs[index]);
    }
    let views = depth_views[best_index];
    best_index_output[gid] = best_index;
    best_score_output[gid] = best_score;
    second_score_output[gid] = second_score;
    views_output[gid] = views;
    if (best_score >= params.ncc_min &&
        best_score - second_score >= params.depth_margin &&
        views >= params.min_views) {
        accepted_output[gid] = 1u;
    } else {
        accepted_output[gid] = 0u;
    }
}
