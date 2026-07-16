#include "colmap/geometry/triangulation.h"
#include "colmap/scene/reconstruction.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <optional>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  if (argc != 3) return 1;
  const std::filesystem::path model_dir = argv[1];
  const std::filesystem::path out_dir = argv[2];
  std::filesystem::create_directories(out_dir);
  colmap::Reconstruction reconstruction;
  reconstruction.Read(model_dir);

  std::ofstream ply(out_dir / "cloud.ply", std::ios::binary);
  ply << "ply\nformat binary_little_endian 1.0\n";
  ply << "element vertex " << reconstruction.NumPoints3D() << "\n";
  ply << "property float x\nproperty float y\nproperty float z\n";
  ply << "property uchar red\nproperty uchar green\nproperty uchar blue\n";
  ply << "end_header\n";
  std::ofstream tracks(out_dir / "track_lengths.csv");
  tracks << "point_index,track_length,stored_reprojection_error_px,"
            "mean_reprojection_error_px,max_reprojection_error_px,"
            "max_triangulation_angle_deg,frame_span\n";
  int point_index = 0;
  for (const auto& [point_id, point] : reconstruction.Points3D()) {
    const float xyz[] = {static_cast<float>(point.xyz.x()),
                         static_cast<float>(point.xyz.y()),
                         static_cast<float>(point.xyz.z())};
    ply.write(reinterpret_cast<const char*>(xyz), sizeof(xyz));
    ply.write(reinterpret_cast<const char*>(point.color.data()), 3);
    std::vector<Eigen::Vector3d> centers;
    centers.reserve(point.track.Length());
    double reprojection_sum = 0.0;
    double reprojection_max = 0.0;
    size_t reprojection_count = 0;
    colmap::image_t min_image_id = std::numeric_limits<colmap::image_t>::max();
    colmap::image_t max_image_id = 0;
    for (const auto& element : point.track.Elements()) {
      if (!reconstruction.ExistsImage(element.image_id)) continue;
      const colmap::Image& image = reconstruction.Image(element.image_id);
      if (!image.HasPose()) continue;
      centers.push_back(image.CamFromWorld().TgtOriginInSrc());
      const Eigen::Vector3d point_cam = image.CamFromWorld() * point.xyz;
      if (point_cam.z() > 0.0 && element.point2D_idx < image.NumPoints2D()) {
        const colmap::Camera* camera = image.CameraPtr();
        const std::optional<Eigen::Vector2d> projected =
            camera == nullptr ? std::nullopt : camera->ImgFromCam(point_cam);
        if (projected.has_value()) {
          const double error =
              (*projected - image.Point2D(element.point2D_idx).xy).norm();
          reprojection_sum += error;
          reprojection_max = std::max(reprojection_max, error);
          ++reprojection_count;
        }
      }
      min_image_id = std::min(min_image_id, element.image_id);
      max_image_id = std::max(max_image_id, element.image_id);
    }
    double max_angle_rad = 0.0;
    for (size_t i = 0; i < centers.size(); ++i) {
      for (size_t j = i + 1; j < centers.size(); ++j) {
        max_angle_rad =
            std::max(max_angle_rad, colmap::CalculateTriangulationAngle(
                                        centers[i], centers[j], point.xyz));
      }
    }
    const auto frame_span = centers.empty() ? 0 : max_image_id - min_image_id;
    const double reprojection_mean =
        reprojection_count > 0 ? reprojection_sum / reprojection_count : -1.0;
    tracks << point_index++ << ',' << point.track.Length() << ',' << point.error
           << ',' << reprojection_mean << ',' << reprojection_max << ','
           << max_angle_rad * 180.0 / M_PI << ',' << frame_span << '\n';
  }

  std::ofstream poses(out_dir / "poses.csv");
  poses << "frame_id,registered,qw,qx,qy,qz,tx,ty,tz\n";
  for (const auto& [image_id, image] : reconstruction.Images()) {
    poses << (static_cast<int>(image_id) - 1) << ',' << (image.HasPose() ? 1 : 0);
    if (image.HasPose()) {
      const auto pose = image.CamFromWorld();
      const auto q = pose.rotation();
      poses << ',' << q.w() << ',' << q.x() << ',' << q.y() << ',' << q.z()
            << ',' << pose.translation().x() << ',' << pose.translation().y()
            << ',' << pose.translation().z();
    } else {
      poses << ",1,0,0,0,0,0,0";
    }
    poses << '\n';
  }
  return 0;
}
