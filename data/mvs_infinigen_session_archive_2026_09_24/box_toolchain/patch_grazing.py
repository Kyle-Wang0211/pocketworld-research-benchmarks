#!/usr/bin/env python3
"""[PW-GRAZING] Task A: grazing-angle guard for AliceVision's visibility ray marching.

Spec source (natural language only, no OpenMVS code copied):
  OpenMVS maintainer cdcseacave, GitHub issue #1165: "views where the camera line of
  sight meets the surface at a back-facing or extreme grazing angle (> 80 deg
  off-normal) are skipped. This prevents grazing camera rays from cutting through
  nearby foreground surfaces."
  Gehrung/Hebel/Arens/Stilla, DGPF Band 27 (2018) p.341: the worst variant of
  Traversionsartefakte is a planar surface crossed at a small incidence angle.

Implementation is original AliceVision-side code (MPL-2). The per-point normal is a
CPU port of AliceVision's OWN normal estimator, not a new invention:
  src/aliceVision/depthMap/cuda/planeSweeping/deviceDepthSimilarityMapKernels.cuh:394
    depthSimMapComputeNormal_kernel<TWsh>
  launched with TWsh=3 from deviceDepthSimilarityMap.cu:180
  PCA helper: src/aliceVision/depthMap/cuda/device/eig33.cuh:351 cuda_stat3d,
              :429 computePlaneByPCA

Switch: --grazingAngleMaxDeg (0.0 = OFF = upstream path, bit-identical).
"""
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/root/av_src"

edits = []  # (path, old, new, label)


def E(path, old, new, label):
    edits.append((path, old, new, label))


# ---------------------------------------------------------------- PointCloud.hpp
E("src/aliceVision/fuseCut/PointCloud.hpp",
  """    const std::vector<int> & getCameraIndices() const
    {
        return _camsVertexes;
    }
""",
  """    const std::vector<int> & getCameraIndices() const
    {
        return _camsVertexes;
    }

    /// [PW-GRAZING] Per-vertex surface normal, oriented towards the camera that produced
    /// the vertex. Either empty (normals disabled) or the same size as getVertices().
    /// A zero-length normal means "no normal available for this vertex" (helper points,
    /// camera centres, degenerate neighbourhoods) and the grazing guard fails open on it.
    const std::vector<Point3d> & getVerticesNormals() const
    {
        return _verticesNormals;
    }
""", "PointCloud.hpp getter")

E("src/aliceVision/fuseCut/PointCloud.hpp",
  """    std::vector<Point3d> _verticesCoords;
    std::vector<GC_vertexInfo> _verticesAttr;
    std::vector<int> _camsVertexes;
""",
  """    std::vector<Point3d> _verticesCoords;
    std::vector<GC_vertexInfo> _verticesAttr;
    std::vector<int> _camsVertexes;
    /// [PW-GRAZING] see getVerticesNormals()
    std::vector<Point3d> _verticesNormals;
""", "PointCloud.hpp member")

# ---------------------------------------------------------------- PointCloud.cpp
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """#include <aliceVision/image/imageAlgo.hpp>

namespace aliceVision {
namespace fuseCut {

namespace fs = std::filesystem;
""",
  """#include <aliceVision/image/imageAlgo.hpp>

#include <Eigen/Eigenvalues>

#include <cmath>

namespace aliceVision {
namespace fuseCut {

namespace fs = std::filesystem;

/// [PW-GRAZING] Estimate the local surface normal at depth-map pixel (x, y) of camera c.
///
/// This is a CPU port of AliceVision's own normal estimator, kept formula-for-formula:
///   depthMap/cuda/planeSweeping/deviceDepthSimilarityMapKernels.cuh:394
///     depthSimMapComputeNormal_kernel<TWsh>, launched with TWsh = 3
///     (deviceDepthSimilarityMap.cu:180)
///   depthMap/cuda/device/eig33.cuh:351 cuda_stat3d / :429 computePlaneByPCA
/// i.e. unweighted PCA over the (2*wsh+1)^2 depth-map window, restricted to neighbours
/// whose depth is within 30 * pixSize of the centre depth; the normal is the eigenvector
/// of the smallest covariance eigenvalue, oriented towards the camera centre.
///
/// Returns a zero vector when no normal can be estimated.
Point3d estimateNormalFromDepthMap(mvsUtils::MultiViewParams& mp, int c, const image::Image<float>& depthMap, int x, int y)
{
    const int wsh = 3;  // same window half-size AliceVision's own kernel is launched with
    const int width = depthMap.width();
    const int height = depthMap.height();

    if (x < 0 || x >= width || y < 0 || y >= height)
        return Point3d(0.0, 0.0, 0.0);

    const double depth = (double)depthMap(y * width + x);
    if (depth <= 0.0)
        return Point3d(0.0, 0.0, 0.0);

    const Point3d p = mp.CArr[c] + (mp.iCamArr[c] * Point2d((double)x, (double)y)).normalize() * depth;
    const Point3d pRight = mp.CArr[c] + (mp.iCamArr[c] * Point2d((double)(x + 1), (double)y)).normalize() * depth;
    const double pixSize = (p - pRight).size();
    if (!(pixSize > 0.0))
        return Point3d(0.0, 0.0, 0.0);

    // first and second order moments of the accepted neighbourhood
    double sx = 0.0, sy = 0.0, sz = 0.0;
    double sxx = 0.0, syy = 0.0, szz = 0.0, sxy = 0.0, sxz = 0.0, syz = 0.0;
    int count = 0;

    for (int yp = -wsh; yp <= wsh; ++yp)
    {
        const int ny = y + yp;
        if (ny < 0 || ny >= height)
            continue;
        for (int xp = -wsh; xp <= wsh; ++xp)
        {
            const int nx = x + xp;
            if (nx < 0 || nx >= width)
                continue;
            const double depthP = (double)depthMap(ny * width + nx);
            if (depthP <= 0.0 || std::fabs(depthP - depth) >= 30.0 * pixSize)
                continue;
            const Point3d pP = mp.CArr[c] + (mp.iCamArr[c] * Point2d((double)nx, (double)ny)).normalize() * depthP;
            sx += pP.x;
            sy += pP.y;
            sz += pP.z;
            sxx += pP.x * pP.x;
            syy += pP.y * pP.y;
            szz += pP.z * pP.z;
            sxy += pP.x * pP.y;
            sxz += pP.x * pP.z;
            syz += pP.y * pP.z;
            ++count;
        }
    }

    if (count < 3)  // same guard as computePlaneByPCA
        return Point3d(0.0, 0.0, 0.0);

    const double n = (double)count;
    const double mx = sx / n, my = sy / n, mz = sz / n;

    Eigen::Matrix3d cov;
    cov(0, 0) = sxx / n - mx * mx;
    cov(1, 1) = syy / n - my * my;
    cov(2, 2) = szz / n - mz * mz;
    cov(0, 1) = cov(1, 0) = sxy / n - mx * my;
    cov(0, 2) = cov(2, 0) = sxz / n - mx * mz;
    cov(1, 2) = cov(2, 1) = syz / n - my * mz;

    Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d> solver(cov);
    if (solver.info() != Eigen::Success)
        return Point3d(0.0, 0.0, 0.0);

    // Eigen sorts eigenvalues in increasing order: column 0 is the plane normal
    const Eigen::Vector3d ev = solver.eigenvectors().col(0);
    Point3d normal(ev.x(), ev.y(), ev.z());
    const double len = normal.size();
    if (!std::isfinite(len) || !(len > 0.0))
        return Point3d(0.0, 0.0, 0.0);
    normal = normal * (1.0 / len);

    // orient towards the camera centre (same sign test as the CUDA kernel)
    const Point3d toCam = (mp.CArr[c] - p).normalize();
    if (dot(normal, toCam) < 0.0)
        normal = -normal;

    return normal;
}
""", "PointCloud.cpp normal estimator")

# --- removeInvalidPoints (3-arg overload): optional normals companion array
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """void removeInvalidPoints(std::vector<Point3d>& verticesCoordsPrepare, std::vector<double>& pixSizePrepare, std::vector<float>& simScorePrepare)
{
    std::vector<Point3d> verticesCoordsTmp;
    verticesCoordsTmp.reserve(verticesCoordsPrepare.size());
    std::vector<double> pixSizeTmp;
    pixSizeTmp.reserve(pixSizePrepare.size());
    std::vector<float> simScoreTmp;
    simScoreTmp.reserve(simScorePrepare.size());
    for (int i = 0; i < verticesCoordsPrepare.size(); ++i)
    {
        if (pixSizePrepare[i] != -1.0)
        {
            verticesCoordsTmp.push_back(verticesCoordsPrepare[i]);
            pixSizeTmp.push_back(pixSizePrepare[i]);
            simScoreTmp.push_back(simScorePrepare[i]);
        }
    }
    ALICEVISION_LOG_INFO((verticesCoordsPrepare.size() - verticesCoordsTmp.size()) << " invalid points removed.");
    verticesCoordsPrepare.swap(verticesCoordsTmp);
    pixSizePrepare.swap(pixSizeTmp);
    simScorePrepare.swap(simScoreTmp);
}""",
  """void removeInvalidPoints(std::vector<Point3d>& verticesCoordsPrepare,
                         std::vector<double>& pixSizePrepare,
                         std::vector<float>& simScorePrepare,
                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */)
{
    std::vector<Point3d> verticesCoordsTmp;
    verticesCoordsTmp.reserve(verticesCoordsPrepare.size());
    std::vector<double> pixSizeTmp;
    pixSizeTmp.reserve(pixSizePrepare.size());
    std::vector<float> simScoreTmp;
    simScoreTmp.reserve(simScorePrepare.size());
    std::vector<Point3d> normalsTmp;
    if (normalsPrepare != nullptr)
        normalsTmp.reserve(normalsPrepare->size());
    for (int i = 0; i < verticesCoordsPrepare.size(); ++i)
    {
        if (pixSizePrepare[i] != -1.0)
        {
            verticesCoordsTmp.push_back(verticesCoordsPrepare[i]);
            pixSizeTmp.push_back(pixSizePrepare[i]);
            simScoreTmp.push_back(simScorePrepare[i]);
            if (normalsPrepare != nullptr)
                normalsTmp.push_back((*normalsPrepare)[i]);
        }
    }
    ALICEVISION_LOG_INFO((verticesCoordsPrepare.size() - verticesCoordsTmp.size()) << " invalid points removed.");
    verticesCoordsPrepare.swap(verticesCoordsTmp);
    pixSizePrepare.swap(pixSizeTmp);
    simScorePrepare.swap(simScoreTmp);
    if (normalsPrepare != nullptr)
        normalsPrepare->swap(normalsTmp);
}""", "PointCloud.cpp removeInvalidPoints/3")

# --- removeInvalidPoints (4-arg overload)
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """void removeInvalidPoints(std::vector<Point3d>& verticesCoordsPrepare,
                         std::vector<double>& pixSizePrepare,
                         std::vector<float>& simScorePrepare,
                         std::vector<GC_vertexInfo>& verticesAttrPrepare)
{
    std::vector<Point3d> verticesCoordsTmp;
    verticesCoordsTmp.reserve(verticesCoordsPrepare.size());
    std::vector<double> pixSizeTmp;
    pixSizeTmp.reserve(pixSizePrepare.size());
    std::vector<float> simScoreTmp;
    simScoreTmp.reserve(simScorePrepare.size());
    std::vector<GC_vertexInfo> verticesAttrTmp;
    verticesAttrTmp.reserve(verticesAttrPrepare.size());
    for (int i = 0; i < verticesCoordsPrepare.size(); ++i)
    {
        if (pixSizePrepare[i] != -1.0)
        {
            verticesCoordsTmp.push_back(verticesCoordsPrepare[i]);
            pixSizeTmp.push_back(pixSizePrepare[i]);
            simScoreTmp.push_back(simScorePrepare[i]);
            verticesAttrTmp.push_back(verticesAttrPrepare[i]);
        }
    }
    ALICEVISION_LOG_INFO((verticesCoordsPrepare.size() - verticesCoordsTmp.size()) << " invalid points removed.");
    verticesCoordsPrepare.swap(verticesCoordsTmp);
    pixSizePrepare.swap(pixSizeTmp);
    simScorePrepare.swap(simScoreTmp);
    verticesAttrPrepare.swap(verticesAttrTmp);
}""",
  """void removeInvalidPoints(std::vector<Point3d>& verticesCoordsPrepare,
                         std::vector<double>& pixSizePrepare,
                         std::vector<float>& simScorePrepare,
                         std::vector<GC_vertexInfo>& verticesAttrPrepare,
                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */)
{
    std::vector<Point3d> verticesCoordsTmp;
    verticesCoordsTmp.reserve(verticesCoordsPrepare.size());
    std::vector<double> pixSizeTmp;
    pixSizeTmp.reserve(pixSizePrepare.size());
    std::vector<float> simScoreTmp;
    simScoreTmp.reserve(simScorePrepare.size());
    std::vector<GC_vertexInfo> verticesAttrTmp;
    verticesAttrTmp.reserve(verticesAttrPrepare.size());
    std::vector<Point3d> normalsTmp;
    if (normalsPrepare != nullptr)
        normalsTmp.reserve(normalsPrepare->size());
    for (int i = 0; i < verticesCoordsPrepare.size(); ++i)
    {
        if (pixSizePrepare[i] != -1.0)
        {
            verticesCoordsTmp.push_back(verticesCoordsPrepare[i]);
            pixSizeTmp.push_back(pixSizePrepare[i]);
            simScoreTmp.push_back(simScorePrepare[i]);
            verticesAttrTmp.push_back(verticesAttrPrepare[i]);
            if (normalsPrepare != nullptr)
                normalsTmp.push_back((*normalsPrepare)[i]);
        }
    }
    ALICEVISION_LOG_INFO((verticesCoordsPrepare.size() - verticesCoordsTmp.size()) << " invalid points removed.");
    verticesCoordsPrepare.swap(verticesCoordsTmp);
    pixSizePrepare.swap(pixSizeTmp);
    simScorePrepare.swap(simScoreTmp);
    verticesAttrPrepare.swap(verticesAttrTmp);
    if (normalsPrepare != nullptr)
        normalsPrepare->swap(normalsTmp);
}""", "PointCloud.cpp removeInvalidPoints/4")

# --- allocate the normals companion array
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """    std::vector<Point3d> verticesCoordsPrepare(realMaxVertices);
    std::vector<double> pixSizePrepare(realMaxVertices);
    std::vector<float> simScorePrepare(realMaxVertices);
""",
  """    std::vector<Point3d> verticesCoordsPrepare(realMaxVertices);
    std::vector<double> pixSizePrepare(realMaxVertices);
    std::vector<float> simScorePrepare(realMaxVertices);

    // [PW-GRAZING] Per-point normals are only estimated (and only carried through the
    // filtering bookkeeping) when the grazing-angle guard is armed, so that the default
    // path stays byte-identical to upstream.
    const bool pwComputeNormals = _mp.userParams.get<double>("delaunaycut.grazingAngleMaxDeg", 0.0) > 0.0;
    std::vector<Point3d> normalsPrepare;
    if (pwComputeNormals)
        normalsPrepare.assign(realMaxVertices, Point3d(0.0, 0.0, 0.0));
    std::vector<Point3d>* pwNormals = pwComputeNormals ? &normalsPrepare : nullptr;
""", "PointCloud.cpp normals array")

# --- fill the normal at the pixel the vertex was taken from
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """                        if (voxel == nullptr || mvsUtils::isPointInHexahedron(p, voxel))
                        {
                            verticesCoordsPrepare[index] = p;
                            simScorePrepare[index] = bestSimScore;
                            pixSizePrepare[index] = _mp.getCamPixelSize(p, c);
                        }""",
  """                        if (voxel == nullptr || mvsUtils::isPointInHexahedron(p, voxel))
                        {
                            verticesCoordsPrepare[index] = p;
                            simScorePrepare[index] = bestSimScore;
                            pixSizePrepare[index] = _mp.getCamPixelSize(p, c);
                            if (pwComputeNormals)
                            {
                                // [PW-GRAZING] normal at the very pixel this vertex comes from
                                normalsPrepare[index] = estimateNormalFromDepthMap(_mp, c, depthMap, bestX, bestY);
                            }
                        }""", "PointCloud.cpp fill normal")

# --- thread the array through the three compaction calls
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """    filterByPixSize(verticesCoordsPrepare, pixSizePrepare, params.pixSizeMarginInitCoef, simScorePrepare);
    // remove points if pixSize == -1
    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare);""",
  """    filterByPixSize(verticesCoordsPrepare, pixSizePrepare, params.pixSizeMarginInitCoef, simScorePrepare);
    // remove points if pixSize == -1
    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, pwNormals);""",
  "PointCloud.cpp compaction 1")

E("src/aliceVision/fuseCut/PointCloud.cpp",
  """    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare);

    ALICEVISION_LOG_INFO("Filter by angle score and sim score");""",
  """    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals);

    ALICEVISION_LOG_INFO("Filter by angle score and sim score");""",
  "PointCloud.cpp compaction 2")

E("src/aliceVision/fuseCut/PointCloud.cpp",
  """        ALICEVISION_LOG_INFO("Remove invalid points.");
        removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare);""",
  """        ALICEVISION_LOG_INFO("Remove invalid points.");
        removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals);""",
  "PointCloud.cpp compaction 3")

# --- publish the normals alongside the coords
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """    // Insert the new elements
    if (_verticesCoords.empty())
    {
        // replace with the new points if empty
        _verticesCoords.swap(verticesCoordsPrepare);
        _verticesAttr.swap(verticesAttrPrepare);
    }
    else
    {
        // concatenate the new elements with the previous ones
        _verticesCoords.insert(_verticesCoords.end(), verticesCoordsPrepare.begin(), verticesCoordsPrepare.end());
        _verticesAttr.insert(_verticesAttr.end(), verticesAttrPrepare.begin(), verticesAttrPrepare.end());
    }""",
  """    // [PW-GRAZING] keep the normals aligned with the coords before they are published
    if (pwComputeNormals)
    {
        if (normalsPrepare.size() != verticesCoordsPrepare.size())
            throw std::runtime_error("[PW-GRAZING] normals/coords size mismatch after fusion filtering.");
        _verticesNormals.resize(_verticesCoords.size(), Point3d(0.0, 0.0, 0.0));
        _verticesNormals.insert(_verticesNormals.end(), normalsPrepare.begin(), normalsPrepare.end());
        std::size_t nbValid = 0;
        for (const Point3d& nrm : normalsPrepare)
            if (nrm.size() > 0.0)
                ++nbValid;
        ALICEVISION_LOG_WARNING("[PW-GRAZING] normals estimated for " << nbValid << " / " << normalsPrepare.size()
                                                                     << " fused points.");
    }

    // Insert the new elements
    if (_verticesCoords.empty())
    {
        // replace with the new points if empty
        _verticesCoords.swap(verticesCoordsPrepare);
        _verticesAttr.swap(verticesAttrPrepare);
    }
    else
    {
        // concatenate the new elements with the previous ones
        _verticesCoords.insert(_verticesCoords.end(), verticesCoordsPrepare.begin(), verticesCoordsPrepare.end());
        _verticesAttr.insert(_verticesAttr.end(), verticesAttrPrepare.begin(), verticesAttrPrepare.end());
    }""", "PointCloud.cpp publish normals")

# --- pad for every point appended after the fusion (all of them only append at the tail)
E("src/aliceVision/fuseCut/PointCloud.cpp",
  """    _verticesCoords.shrink_to_fit();
    _verticesAttr.shrink_to_fit();
""",
  """    // [PW-GRAZING] every point added after fuseFromDepthMaps (SfM landmarks, camera
    // centres, densify/grid/singularity/mask helper points) is only ever appended at the
    // tail, so padding with zero normals keeps index alignment. Zero == "no normal", on
    // which the guard fails open.
    if (!_verticesNormals.empty())
    {
        _verticesNormals.resize(_verticesCoords.size(), Point3d(0.0, 0.0, 0.0));
        _verticesNormals.shrink_to_fit();
    }

    _verticesCoords.shrink_to_fit();
    _verticesAttr.shrink_to_fit();
""", "PointCloud.cpp pad normals")

# ---------------------------------------------------------------- GraphFiller.hpp
E("src/aliceVision/fuseCut/GraphFiller.hpp",
  """#include <aliceVision/fuseCut/Intersections.hpp>


namespace aliceVision {""",
  """#include <aliceVision/fuseCut/Intersections.hpp>

#include <atomic>
#include <cstdint>


namespace aliceVision {""", "GraphFiller.hpp includes")

E("src/aliceVision/fuseCut/GraphFiller.hpp",
  """    void forceTedgesByGradientIJCV(float nPixelSizeBehind);

    std::vector<CellIndex> getNeighboringCellsByGeometry(const GeometryIntersection& g) const;

private:
    const Tetrahedralization & _tetrahedralization;
    const std::vector<Point3d> & _verticesCoords;
    const std::vector<GC_vertexInfo> & _verticesAttr;
    const std::vector<int> & _camsVertexes;
""",
  """    void forceTedgesByGradientIJCV(float nPixelSizeBehind);

    std::vector<CellIndex> getNeighboringCellsByGeometry(const GeometryIntersection& g) const;

    /// [PW-GRAZING] True when the line of sight from \\p cam to vertex \\p vertexIndex meets the
    /// local surface at a back-facing or extreme grazing angle, in which case that ray must not
    /// vote. Always false when the guard is disabled or no normal is available (fail open).
    /// \\p countStats must be true for exactly one call per (vertex, cam) pair.
    bool isGrazingRay(int vertexIndex, int cam, bool countStats) const;

private:
    const Tetrahedralization & _tetrahedralization;
    const std::vector<Point3d> & _verticesCoords;
    const std::vector<GC_vertexInfo> & _verticesAttr;
    const std::vector<int> & _camsVertexes;
    /// [PW-GRAZING] per-vertex normals; empty when the guard is disabled
    const std::vector<Point3d> & _verticesNormals;
""", "GraphFiller.hpp members")

E("src/aliceVision/fuseCut/GraphFiller.hpp",
  """    mvsUtils::MultiViewParams& _mp;
    std::vector<GC_cellInfo> _cellsAttr;
    std::vector<bool> _cellIsFull;
};""",
  """    mvsUtils::MultiViewParams& _mp;
    std::vector<GC_cellInfo> _cellsAttr;
    std::vector<bool> _cellIsFull;

    // [PW-GRAZING] grazing-angle guard state
    bool _grazingGuardEnabled = false;
    double _grazingCosMin = -2.0;
    mutable std::atomic<std::uint64_t> _grazingTested{0};
    mutable std::atomic<std::uint64_t> _grazingSkipped{0};
    mutable std::atomic<std::uint64_t> _grazingNoNormal{0};
};""", "GraphFiller.hpp guard state")

# ---------------------------------------------------------------- GraphFiller.cpp
E("src/aliceVision/fuseCut/GraphFiller.cpp",
  """#include <boost/atomic/atomic_ref.hpp>
""",
  """#include <boost/atomic/atomic_ref.hpp>

#include <cmath>
""", "GraphFiller.cpp includes")

E("src/aliceVision/fuseCut/GraphFiller.cpp",
  """  _verticesAttr(pc.getVerticesAttrs()),
  _camsVertexes(pc.getCameraIndices()),
  _tetrahedralization(tetrahedralization)""",
  """  _verticesAttr(pc.getVerticesAttrs()),
  _camsVertexes(pc.getCameraIndices()),
  _verticesNormals(pc.getVerticesNormals()),
  _tetrahedralization(tetrahedralization)""", "GraphFiller.cpp ctor")

E("src/aliceVision/fuseCut/GraphFiller.cpp",
  """    const bool forceTEdge = _mp.userParams.get<bool>("delaunaycut.voteFilteringForWeaklySupportedSurfaces", true);

    addToInfiniteSw((float)maxint);

    fillGraph(nPixelSizeBehind, fullWeight);
""",
  """    const bool forceTEdge = _mp.userParams.get<bool>("delaunaycut.voteFilteringForWeaklySupportedSurfaces", true);

    // [PW-GRAZING] Grazing-angle guard. 0 (the default) keeps the upstream code path.
    // Spec: OpenMVS maintainer cdcseacave in github.com/cdcseacave/openMVS issue #1165 --
    // "views where the camera line of sight meets the surface at a back-facing or extreme
    // grazing angle (> 80 deg off-normal) are skipped"; and Gehrung/Hebel/Arens/Stilla,
    // DGPF Band 27 (2018) p.341 on Traversionsartefakte at small incidence angles.
    // No OpenMVS code is reused here; only the stated rule.
    const double grazingAngleMaxDeg = _mp.userParams.get<double>("delaunaycut.grazingAngleMaxDeg", 0.0);
    _grazingGuardEnabled = (grazingAngleMaxDeg > 0.0) && (grazingAngleMaxDeg < 180.0);
    _grazingCosMin = std::cos(grazingAngleMaxDeg * M_PI / 180.0);
    _grazingTested = 0;
    _grazingSkipped = 0;
    _grazingNoNormal = 0;
    if (_grazingGuardEnabled)
    {
        if (_verticesNormals.empty())
        {
            ALICEVISION_LOG_ERROR("[PW-GRAZING] guard requested (" << grazingAngleMaxDeg
                                  << " deg) but no per-vertex normals are available: guard stays inactive.");
            _grazingGuardEnabled = false;
        }
        else
        {
            ALICEVISION_LOG_WARNING("[PW-GRAZING] guard ENABLED: maxAngleOffNormal=" << grazingAngleMaxDeg
                                    << " deg, cosMin=" << _grazingCosMin << ", normals for " << _verticesNormals.size()
                                    << " vertices (coords: " << _verticesCoords.size() << ").");
        }
    }
    else
    {
        ALICEVISION_LOG_INFO("[PW-GRAZING] guard DISABLED (grazingAngleMaxDeg=" << grazingAngleMaxDeg << ").");
    }

    addToInfiniteSw((float)maxint);

    fillGraph(nPixelSizeBehind, fullWeight);

    if (_grazingGuardEnabled)
    {
        const std::uint64_t tested = _grazingTested.load();
        const std::uint64_t skipped = _grazingSkipped.load();
        const std::uint64_t noNormal = _grazingNoNormal.load();
        ALICEVISION_LOG_WARNING("[PW-GRAZING] rays tested: " << tested << ", skipped: " << skipped << " ("
                                << (tested ? (100.0 * double(skipped) / double(tested)) : 0.0)
                                << "%), no-normal (fail open): " << noNormal << ".");
    }
""", "GraphFiller.cpp build guard setup")

E("src/aliceVision/fuseCut/GraphFiller.cpp",
  """void GraphFiller::rayMarchingGraphEmpty(int vertexIndex,
                                         int cam,
                                         float weight)
{
    const int maxint = std::numeric_limits<int>::max();
""",
  """bool GraphFiller::isGrazingRay(int vertexIndex, int cam, bool countStats) const
{
    if (!_grazingGuardEnabled)
    {
        return false;
    }

    // Fail open when this vertex carries no usable normal (helper points, camera centres,
    // degenerate PCA neighbourhoods): those rays keep voting exactly as upstream.
    const bool hasNormal = (vertexIndex >= 0) && (std::size_t(vertexIndex) < _verticesNormals.size()) &&
                           (_verticesNormals[vertexIndex].size() > 0.0);
    if (!hasNormal)
    {
        if (countStats)
        {
            _grazingNoNormal.fetch_add(1, std::memory_order_relaxed);
        }
        return false;
    }

    const Point3d& normal = _verticesNormals[vertexIndex];
    const Point3d toCam = _mp.CArr[cam] - _verticesCoords[vertexIndex];
    const double toCamLen = toCam.size();
    if (!(toCamLen > 0.0))
    {
        if (countStats)
        {
            _grazingNoNormal.fetch_add(1, std::memory_order_relaxed);
        }
        return false;
    }

    // normals are oriented towards the camera that produced the vertex, so cosAngle is the
    // cosine of the angle between the line of sight and the surface normal.
    const double cosAngle = dot(normal, toCam) / (normal.size() * toCamLen);

    const bool grazing = (cosAngle < _grazingCosMin);
    if (countStats)
    {
        _grazingTested.fetch_add(1, std::memory_order_relaxed);
        if (grazing)
        {
            _grazingSkipped.fetch_add(1, std::memory_order_relaxed);
        }
    }
    return grazing;
}

void GraphFiller::rayMarchingGraphEmpty(int vertexIndex,
                                         int cam,
                                         float weight)
{
    // [PW-GRAZING] back-facing / extreme grazing lines of sight are not allowed to vote.
    // This is the one call per (vertex, cam) pair that updates the statistics.
    if (isGrazingRay(vertexIndex, cam, true))
    {
        return;
    }

    const int maxint = std::numeric_limits<int>::max();
""", "GraphFiller.cpp guard in rayMarchingGraphEmpty")

E("src/aliceVision/fuseCut/GraphFiller.cpp",
  """void GraphFiller::rayMarchingGraphFull(int vertexIndex,
                                         int cam,
                                         float fullWeight,
                                         double nPixelSizeBehind)
{
    assert(cam >= 0);""",
  """void GraphFiller::rayMarchingGraphFull(int vertexIndex,
                                         int cam,
                                         float fullWeight,
                                         double nPixelSizeBehind)
{
    // [PW-GRAZING] same guard as the EMPTY pass: the whole line of sight is discarded, so the
    // FULL margin behind the vertex is not voted for either. Statistics are counted in the
    // EMPTY pass only, which runs first for the same (vertex, cam) pair.
    if (isGrazingRay(vertexIndex, cam, false))
    {
        return;
    }

    assert(cam >= 0);""", "GraphFiller.cpp guard in rayMarchingGraphFull")

# ---------------------------------------------------------------- main_meshing.cpp
E("src/software/pipeline/main_meshing.cpp",
  """    double nPixelSizeBehind = 4.0;
    double fullWeight = 1.0;
""",
  """    double nPixelSizeBehind = 4.0;
    double fullWeight = 1.0;
    double grazingAngleMaxDeg = 0.0;  // [PW-GRAZING] 0 = guard off = upstream behaviour
""", "main_meshing decl")

E("src/software/pipeline/main_meshing.cpp",
  """        ("fullWeight", po::value<double>(&fullWeight)->default_value(fullWeight),
         "Weighting of the FULL cells.")
""",
  """        ("fullWeight", po::value<double>(&fullWeight)->default_value(fullWeight),
         "Weighting of the FULL cells.")
        ("grazingAngleMaxDeg", po::value<double>(&grazingAngleMaxDeg)->default_value(grazingAngleMaxDeg),
         "[PW-GRAZING] Grazing-angle guard for the visibility ray marching: a line of sight whose angle to the "
         "local surface normal exceeds this value (degrees, so back-facing rays are always above it) does not "
         "vote. 0 disables the guard and keeps the upstream code path.")
""", "main_meshing option")

E("src/software/pipeline/main_meshing.cpp",
  """    mp.userParams.put("delaunaycut.fullWeight", fullWeight);
""",
  """    mp.userParams.put("delaunaycut.fullWeight", fullWeight);
    mp.userParams.put("delaunaycut.grazingAngleMaxDeg", grazingAngleMaxDeg);
""", "main_meshing userParams")


def main():
    failures = []
    # group edits per file so each file is read/written once
    from collections import OrderedDict
    byfile = OrderedDict()
    for path, old, new, label in edits:
        byfile.setdefault(path, []).append((old, new, label))

    for path, ops in byfile.items():
        full = f"{ROOT}/{path}"
        with open(full, "r", encoding="utf-8") as fh:
            text = fh.read()
        for old, new, label in ops:
            cnt = text.count(old)
            if cnt != 1:
                failures.append(f"{label}: anchor found {cnt} times in {path}")
                continue
            text = text.replace(old, new, 1)
            print(f"  ok  {label}")
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  !! " + f)
        sys.exit(1)
    print("\nALL EDITS APPLIED")


main()
