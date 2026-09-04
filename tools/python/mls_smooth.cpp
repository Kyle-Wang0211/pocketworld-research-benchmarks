// MLS surface smoothing via PCL's pcl::MovingLeastSquares (BSD, SOTA — not self-written).
// Smooths grazing-floor curl + depth jitter and pulls floaters onto the local surface,
// while keeping the cloud a point cloud. This is the C++/FFI form we'd reuse on iOS/Android/HarmonyOS.
//
// usage: mls_smooth in.ply out.ply search_radius [poly_order=2]
#include <pcl/io/ply_io.h>
#include <pcl/point_types.h>
#include <pcl/surface/mls.h>
#include <pcl/search/kdtree.h>
#include <pcl/kdtree/kdtree_flann.h>
#include <iostream>

int main(int argc, char** argv) {
  if (argc < 4) { std::cerr << "usage: mls_smooth in.ply out.ply radius [poly_order]\n"; return 1; }
  const float radius = std::stof(argv[3]);
  const int order = argc > 4 ? std::stoi(argv[4]) : 2;

  pcl::PointCloud<pcl::PointXYZRGB>::Ptr in(new pcl::PointCloud<pcl::PointXYZRGB>);
  if (pcl::io::loadPLYFile(argv[1], *in) < 0) { std::cerr << "load fail: " << argv[1] << "\n"; return 1; }
  std::cerr << "loaded " << in->size() << " pts; MLS radius=" << radius << " order=" << order << "\n";

  pcl::search::KdTree<pcl::PointXYZRGB>::Ptr tree(new pcl::search::KdTree<pcl::PointXYZRGB>);
  pcl::MovingLeastSquares<pcl::PointXYZRGB, pcl::PointXYZRGB> mls;
  mls.setComputeNormals(false);
  mls.setInputCloud(in);
  mls.setPolynomialOrder(order);
  mls.setSearchMethod(tree);
  mls.setSearchRadius(radius);
  pcl::PointCloud<pcl::PointXYZRGB>::Ptr out(new pcl::PointCloud<pcl::PointXYZRGB>);
  mls.process(*out);
  std::cerr << "after MLS: " << out->size() << " pts\n";

  // MLS may not carry RGB through the projection -> re-attach color from the nearest input point.
  bool need_color = true;
  for (size_t i = 0; i < std::min<size_t>(out->size(), 1000); ++i)
    if (out->points[i].r || out->points[i].g || out->points[i].b) { need_color = false; break; }
  if (need_color && !out->empty()) {
    std::cerr << "re-attaching color via nearest input point\n";
    pcl::KdTreeFLANN<pcl::PointXYZRGB> kt; kt.setInputCloud(in);
    std::vector<int> idx(1); std::vector<float> d2(1);
    for (auto& p : out->points)
      if (kt.nearestKSearch(p, 1, idx, d2) > 0) {
        const auto& s = in->points[idx[0]]; p.r = s.r; p.g = s.g; p.b = s.b;
      }
  }
  pcl::io::savePLYFileBinary(argv[2], *out);
  std::cerr << "wrote " << argv[2] << "\n";
  return 0;
}
