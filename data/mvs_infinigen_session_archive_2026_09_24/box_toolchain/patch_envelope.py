#!/usr/bin/env python3
"""[PW-ENVELOPE] Task B: make the "same layer" bandwidth the MATCHER'S OWN per-pixel
search interval instead of a fixed multiple of the pixel footprint.

Mechanism source (MicMac, no third criterion invented):
  DocMicMac/DocProg/MMCourse_day_4-5_matching.tex:219 -- ComputePx creates a "matching
  envelope" constrained by aTEnvInf/aTEnvSup, "a region in the parallax space that will be
  exploited during matching ... as the matching proceeds at higher resolution levels, the
  search space adjusts to the true 3D object scene".
  MicMac cASAMG.cpp:185-191 InterioriteEnvlop uses that same quantity as the "same surface"
  bandwidth.

Upstream AliceVision bandwidth (what we replace), PointCloud.cpp:
  filterByPixSize:                 pixSizeScore = pixSizeMarginCoef * simScore * pixSize^2
  createVerticesWithVisibilities:  pixSizeScoreI = simScore * pixSize^2
                                   pixSizeScoreV = simScore * pixSizeV^2
  gates: dist2 < voteMarginFactor * max(I, V)  and  dist2 < contributeMarginFactor * V

With --matchEnvelopeFolder set, simScore*pixSize^2 is replaced by env^2, where env is the
metric (SfM-unit) half-width of CasDiffMVS's own per-pixel search interval, precomputed by
make_envmaps.py from CasDiffMVS's verbatim formula (models/module.py:263-268) and its
disp->depth Jacobian (module.py:220-227). The voteMarginFactor / contributeMarginFactor /
pixSizeMarginCoef multipliers are left exactly as upstream, so the ONE variable that changes
is what the bandwidth is proportional to.

Empty folder (the default) => upstream code path, untouched.
"""
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "/root/av_src"
edits = []


def E(path, old, new, label):
    edits.append((path, old, new, label))


PC = "src/aliceVision/fuseCut/PointCloud.cpp"

# ---------------------------------------------------------------- env map loader
E(PC,
  """/// Filter by pixSize
void filterByPixSize(const std::vector<Point3d>& verticesCoordsPrepare,
                     std::vector<double>& pixSizePrepare,
                     double pixSizeMarginCoef,
                     std::vector<float>& simScorePrepare)
{
""",
  """/// [PW-ENVELOPE] Read the per-pixel matching-envelope half-width map of camera \\p c, in SfM
/// units. Returns false when no such map exists (the caller then keeps the upstream path).
bool pwReadEnvelopeMap(mvsUtils::MultiViewParams& mp, int c, const std::string& folder, image::Image<float>& out)
{
    if (folder.empty())
        return false;
    const std::string path = folder + "/" + std::to_string(mp.getViewId(c)) + "_envMap.exr";
    if (!utils::exists(path))
    {
        ALICEVISION_LOG_WARNING("[PW-ENVELOPE] envelope map not found: " << path);
        return false;
    }
    image::readImage(path, out, image::EImageColorSpace::NO_CONVERSION);
    if (out.width() != mp.getWidth(c) || out.height() != mp.getHeight(c))
    {
        ALICEVISION_LOG_ERROR("[PW-ENVELOPE] envelope map size mismatch for cam " << c << " (" << out.width() << "x"
                              << out.height() << " vs " << mp.getWidth(c) << "x" << mp.getHeight(c) << ")");
        return false;
    }
    return true;
}

/// Filter by pixSize
void filterByPixSize(const std::vector<Point3d>& verticesCoordsPrepare,
                     std::vector<double>& pixSizePrepare,
                     double pixSizeMarginCoef,
                     std::vector<float>& simScorePrepare,
                     const std::vector<float>* envPrepare /* [PW-ENVELOPE] nullptr = upstream */)
{
""", "env map loader + filterByPixSize signature")

E(PC,
  """        const double pixSizeScore = pixSizeMarginCoef * simScorePrepare[vIndex] * pixSizePrepare[vIndex] * pixSizePrepare[vIndex];
        if (pixSizeScore < std::numeric_limits<double>::epsilon())""",
  """        // [PW-ENVELOPE] bandwidth = the matcher's own search interval, when supplied
        double pixSizeScore;
        if (envPrepare != nullptr)
        {
            const double env = (*envPrepare)[vIndex];
            pixSizeScore = (env > 0.0) ? (pixSizeMarginCoef * env * env) : 0.0;
        }
        else
        {
            pixSizeScore = pixSizeMarginCoef * simScorePrepare[vIndex] * pixSizePrepare[vIndex] * pixSizePrepare[vIndex];
        }
        if (pixSizeScore < std::numeric_limits<double>::epsilon())""",
  "filterByPixSize bandwidth")

# ---------------------------------------------------------------- removeInvalidPoints: carry env
E(PC,
  """                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */)
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
}""",
  """                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */,
                         std::vector<float>* envPrepare /* [PW-ENVELOPE] nullptr = upstream behaviour */)
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
    std::vector<float> envTmp;
    if (envPrepare != nullptr)
        envTmp.reserve(envPrepare->size());
    for (int i = 0; i < verticesCoordsPrepare.size(); ++i)
    {
        if (pixSizePrepare[i] != -1.0)
        {
            verticesCoordsTmp.push_back(verticesCoordsPrepare[i]);
            pixSizeTmp.push_back(pixSizePrepare[i]);
            simScoreTmp.push_back(simScorePrepare[i]);
            if (normalsPrepare != nullptr)
                normalsTmp.push_back((*normalsPrepare)[i]);
            if (envPrepare != nullptr)
                envTmp.push_back((*envPrepare)[i]);
        }
    }
    ALICEVISION_LOG_INFO((verticesCoordsPrepare.size() - verticesCoordsTmp.size()) << " invalid points removed.");
    verticesCoordsPrepare.swap(verticesCoordsTmp);
    pixSizePrepare.swap(pixSizeTmp);
    simScorePrepare.swap(simScoreTmp);
    if (normalsPrepare != nullptr)
        normalsPrepare->swap(normalsTmp);
    if (envPrepare != nullptr)
        envPrepare->swap(envTmp);
}""", "removeInvalidPoints/3 carry env")

E(PC,
  """                         std::vector<GC_vertexInfo>& verticesAttrPrepare,
                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */)
{""",
  """                         std::vector<GC_vertexInfo>& verticesAttrPrepare,
                         std::vector<Point3d>* normalsPrepare /* [PW-GRAZING] nullptr = upstream behaviour */,
                         std::vector<float>* envPrepare /* [PW-ENVELOPE] nullptr = upstream behaviour */)
{""", "removeInvalidPoints/4 signature")

E(PC,
  """    std::vector<Point3d> normalsTmp;
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
    }""",
  """    std::vector<Point3d> normalsTmp;
    if (normalsPrepare != nullptr)
        normalsTmp.reserve(normalsPrepare->size());
    std::vector<float> envTmp;
    if (envPrepare != nullptr)
        envTmp.reserve(envPrepare->size());
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
            if (envPrepare != nullptr)
                envTmp.push_back((*envPrepare)[i]);
        }
    }""", "removeInvalidPoints/4 carry env loop")

E(PC,
  """    verticesAttrPrepare.swap(verticesAttrTmp);
    if (normalsPrepare != nullptr)
        normalsPrepare->swap(normalsTmp);
}""",
  """    verticesAttrPrepare.swap(verticesAttrTmp);
    if (normalsPrepare != nullptr)
        normalsPrepare->swap(normalsTmp);
    if (envPrepare != nullptr)
        envPrepare->swap(envTmp);
}""", "removeInvalidPoints/4 carry env swap")

# ---------------------------------------------------------------- createVerticesWithVisibilities
E(PC,
  """                                    float voteMarginFactor,
                                    float contributeMarginFactor,
                                    float simGaussianSize)
{
""",
  """                                    float voteMarginFactor,
                                    float contributeMarginFactor,
                                    float simGaussianSize,
                                    const std::vector<float>* envPrepare /* [PW-ENVELOPE] nullptr = upstream */,
                                    const std::string& envFolder)
{
""", "createVerticesWithVisibilities signature")

E(PC,
  """        // read similarity map
        try
        {
            mvsUtils::readMap(c, mp, mvsUtils::EFileType::simMapFiltered, simMap);
            image::Image<float> simMapTmp(simMap.width(), simMap.height());
            imageAlgo::convolveImage(simMap, simMapTmp, "gaussian", simGaussianSize, simGaussianSize);
            simMap.swap(simMapTmp);
        }
        catch (const std::exception& e)
        {
            ALICEVISION_LOG_WARNING("Cannot find similarity map file.");
            simMap.resize(width * height, -1);
        }
""",
  """        // read similarity map
        try
        {
            mvsUtils::readMap(c, mp, mvsUtils::EFileType::simMapFiltered, simMap);
            image::Image<float> simMapTmp(simMap.width(), simMap.height());
            imageAlgo::convolveImage(simMap, simMapTmp, "gaussian", simGaussianSize, simGaussianSize);
            simMap.swap(simMapTmp);
        }
        catch (const std::exception& e)
        {
            ALICEVISION_LOG_WARNING("Cannot find similarity map file.");
            simMap.resize(width * height, -1);
        }

        // [PW-ENVELOPE] per-pixel matching envelope half-width of this camera
        image::Image<float> envMap;
        const bool pwUseEnv = (envPrepare != nullptr) && pwReadEnvelopeMap(mp, c, envFolder, envMap);
""", "createVerticesWithVisibilities load env")

E(PC,
  """                const float pixSizeScoreI = simScorePrepare[nearestVertexIndex] * pixSize * pixSize;
                const float pixSizeScoreV =
                  simScorePrepare[nearestVertexIndex] * pixSizePrepare[nearestVertexIndex] * pixSizePrepare[nearestVertexIndex];
""",
  """                // [PW-ENVELOPE] bandwidth = the matcher's own per-pixel search interval, when supplied
                float pixSizeScoreI;
                float pixSizeScoreV;
                if (pwUseEnv)
                {
                    const float envI = envMap(index);
                    const float envV = (*envPrepare)[nearestVertexIndex];
                    if (!(envI > 0.0f) || !(envV > 0.0f))
                        continue;  // no envelope here: this observation cannot be attributed
                    pixSizeScoreI = envI * envI;
                    pixSizeScoreV = envV * envV;
                }
                else
                {
                    pixSizeScoreI = simScorePrepare[nearestVertexIndex] * pixSize * pixSize;
                    pixSizeScoreV =
                      simScorePrepare[nearestVertexIndex] * pixSizePrepare[nearestVertexIndex] * pixSizePrepare[nearestVertexIndex];
                }
""", "createVerticesWithVisibilities bandwidth")

# ---------------------------------------------------------------- fuseFromDepthMaps wiring
E(PC,
  """    std::vector<Point3d> normalsPrepare;
    if (pwComputeNormals)
        normalsPrepare.assign(realMaxVertices, Point3d(0.0, 0.0, 0.0));
    std::vector<Point3d>* pwNormals = pwComputeNormals ? &normalsPrepare : nullptr;
""",
  """    std::vector<Point3d> normalsPrepare;
    if (pwComputeNormals)
        normalsPrepare.assign(realMaxVertices, Point3d(0.0, 0.0, 0.0));
    std::vector<Point3d>* pwNormals = pwComputeNormals ? &normalsPrepare : nullptr;

    // [PW-ENVELOPE] matcher-envelope bandwidth. Empty folder => upstream path, no extra work.
    const std::string pwEnvFolder = _mp.userParams.get<std::string>("delaunaycut.matchEnvelopeFolder", "");
    const bool pwUseEnvelope = !pwEnvFolder.empty();
    std::vector<float> envPrepare;
    if (pwUseEnvelope)
        envPrepare.assign(realMaxVertices, -1.0f);
    std::vector<float>* pwEnv = pwUseEnvelope ? &envPrepare : nullptr;
    if (pwUseEnvelope)
        ALICEVISION_LOG_WARNING("[PW-ENVELOPE] bandwidth = matcher search interval, maps from: " << pwEnvFolder);
""", "fuseFromDepthMaps env array")

E(PC,
  """            const int syMax = divideRoundUp(height, step);
            const int sxMax = divideRoundUp(width, step);""",
  """            // [PW-ENVELOPE] envelope map of this camera, read once per camera
            image::Image<float> envMapCam;
            const bool pwCamHasEnv = pwUseEnvelope && pwReadEnvelopeMap(_mp, c, pwEnvFolder, envMapCam);

            const int syMax = divideRoundUp(height, step);
            const int sxMax = divideRoundUp(width, step);""", "fuseFromDepthMaps load env per cam")

E(PC,
  """                            if (pwComputeNormals)
                            {
                                // [PW-GRAZING] normal at the very pixel this vertex comes from
                                normalsPrepare[index] = estimateNormalFromDepthMap(_mp, c, depthMap, bestX, bestY);
                            }""",
  """                            if (pwComputeNormals)
                            {
                                // [PW-GRAZING] normal at the very pixel this vertex comes from
                                normalsPrepare[index] = estimateNormalFromDepthMap(_mp, c, depthMap, bestX, bestY);
                            }
                            if (pwCamHasEnv)
                            {
                                // [PW-ENVELOPE] envelope half-width at the very pixel this vertex comes from
                                envPrepare[index] = envMapCam(bestY * width + bestX);
                            }""", "fuseFromDepthMaps fill env")

E(PC,
  """    filterByPixSize(verticesCoordsPrepare, pixSizePrepare, params.pixSizeMarginInitCoef, simScorePrepare);
    // remove points if pixSize == -1
    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, pwNormals);""",
  """    filterByPixSize(verticesCoordsPrepare, pixSizePrepare, params.pixSizeMarginInitCoef, simScorePrepare, pwEnv);
    // remove points if pixSize == -1
    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, pwNormals, pwEnv);""",
  "wire compaction 1")

E(PC,
  """    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals);

    ALICEVISION_LOG_INFO("Filter by angle score and sim score");""",
  """    removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals, pwEnv);

    ALICEVISION_LOG_INFO("Filter by angle score and sim score");""",
  "wire compaction 2")

E(PC,
  """        filterByPixSize(verticesCoordsPrepare, pixSizePrepare, pixSizeMarginFinalCoef, simScorePrepare);

        ALICEVISION_LOG_INFO("Remove invalid points.");
        removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals);""",
  """        filterByPixSize(verticesCoordsPrepare, pixSizePrepare, pixSizeMarginFinalCoef, simScorePrepare, pwEnv);

        ALICEVISION_LOG_INFO("Remove invalid points.");
        removeInvalidPoints(verticesCoordsPrepare, pixSizePrepare, simScorePrepare, verticesAttrPrepare, pwNormals, pwEnv);""",
  "wire compaction 3 + final filter")

# both createVerticesWithVisibilities call sites
E(PC,
  """    createVerticesWithVisibilities(cams,
                                   verticesCoordsPrepare,
                                   pixSizePrepare,
                                   simScorePrepare,
                                   verticesAttrPrepare,
                                   _mp,
                                   params.simFactor,
                                   params.voteMarginFactor,
                                   params.contributeMarginFactor,
                                   params.simGaussianSize);

    ALICEVISION_LOG_INFO("Compute max angle per point");""",
  """    createVerticesWithVisibilities(cams,
                                   verticesCoordsPrepare,
                                   pixSizePrepare,
                                   simScorePrepare,
                                   verticesAttrPrepare,
                                   _mp,
                                   params.simFactor,
                                   params.voteMarginFactor,
                                   params.contributeMarginFactor,
                                   params.simGaussianSize,
                                   pwEnv,
                                   pwEnvFolder);

    ALICEVISION_LOG_INFO("Compute max angle per point");""", "wire createVertices call 1")

E(PC,
  """        createVerticesWithVisibilities(cams,
                                       verticesCoordsPrepare,
                                       pixSizePrepare,
                                       simScorePrepare,
                                       verticesAttrPrepare,
                                       _mp,
                                       params.simFactor,
                                       params.voteMarginFactor,
                                       params.contributeMarginFactor,
                                       params.simGaussianSize);""",
  """        createVerticesWithVisibilities(cams,
                                       verticesCoordsPrepare,
                                       pixSizePrepare,
                                       simScorePrepare,
                                       verticesAttrPrepare,
                                       _mp,
                                       params.simFactor,
                                       params.voteMarginFactor,
                                       params.contributeMarginFactor,
                                       params.simGaussianSize,
                                       pwEnv,
                                       pwEnvFolder);""", "wire createVertices call 2")

# report what the envelope actually looked like on the points that survived
E(PC,
  """    ALICEVISION_LOG_WARNING("fuseFromDepthMaps done: " << verticesCoordsPrepare.size() << " points created.");""",
  """    if (pwUseEnvelope)
    {
        std::vector<float> v;
        v.reserve(envPrepare.size());
        for (float e : envPrepare)
            if (e > 0.0f)
                v.push_back(e);
        if (!v.empty())
        {
            std::sort(v.begin(), v.end());
            auto pc = [&v](double q) { return v[std::min(v.size() - 1, std::size_t(q * v.size()))]; };
            ALICEVISION_LOG_WARNING("[PW-ENVELOPE] surviving-point envelope half-width (SfM units): n=" << v.size()
                                    << " p5=" << pc(0.05) << " p50=" << pc(0.50) << " p95=" << pc(0.95)
                                    << " max=" << v.back());
        }
        else
        {
            ALICEVISION_LOG_ERROR("[PW-ENVELOPE] no surviving point carries an envelope value.");
        }
    }

    ALICEVISION_LOG_WARNING("fuseFromDepthMaps done: " << verticesCoordsPrepare.size() << " points created.");""",
  "envelope stats log")

# ---------------------------------------------------------------- main_meshing.cpp
MM = "src/software/pipeline/main_meshing.cpp"
E(MM,
  """    double grazingAngleMaxDeg = 0.0;  // [PW-GRAZING] 0 = guard off = upstream behaviour
""",
  """    double grazingAngleMaxDeg = 0.0;  // [PW-GRAZING] 0 = guard off = upstream behaviour
    std::string matchEnvelopeFolder;   // [PW-ENVELOPE] empty = off = upstream behaviour
""", "main_meshing env decl")

E(MM,
  """        ("grazingAngleMaxDeg", po::value<double>(&grazingAngleMaxDeg)->default_value(grazingAngleMaxDeg),""",
  """        ("matchEnvelopeFolder", po::value<std::string>(&matchEnvelopeFolder)->default_value(matchEnvelopeFolder),
         "[PW-ENVELOPE] Folder of per-view <viewId>_envMap.exr maps holding the matcher's own per-pixel search "
         "interval half-width in SfM units. When set, the 'same layer' bandwidth becomes that envelope instead of "
         "simScore * pixSize^2. Empty (default) keeps the upstream code path.")
        ("grazingAngleMaxDeg", po::value<double>(&grazingAngleMaxDeg)->default_value(grazingAngleMaxDeg),""",
  "main_meshing env option")

E(MM,
  """    mp.userParams.put("delaunaycut.grazingAngleMaxDeg", grazingAngleMaxDeg);
""",
  """    mp.userParams.put("delaunaycut.grazingAngleMaxDeg", grazingAngleMaxDeg);
    mp.userParams.put("delaunaycut.matchEnvelopeFolder", matchEnvelopeFolder);
""", "main_meshing env userParams")


def main():
    from collections import OrderedDict
    byfile = OrderedDict()
    for path, old, new, label in edits:
        byfile.setdefault(path, []).append((old, new, label))
    failures = []
    for path, ops in byfile.items():
        full = f"{ROOT}/{path}"
        text = open(full, encoding="utf-8").read()
        for old, new, label in ops:
            cnt = text.count(old)
            if cnt != 1:
                failures.append(f"{label}: anchor found {cnt} times in {path}")
                continue
            text = text.replace(old, new, 1)
            print(f"  ok  {label}")
        open(full, "w", encoding="utf-8").write(text)
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  !! " + f)
        sys.exit(1)
    print("\nALL EDITS APPLIED")


main()
