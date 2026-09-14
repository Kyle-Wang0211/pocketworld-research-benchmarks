import marshal, types, sys, os
def strings(p):
    data=open(p,"rb").read()
    code=marshal.loads(data[16:])
    out=[]
    def walk(c):
        for k in c.co_consts:
            if isinstance(k,types.CodeType): walk(k)
            elif isinstance(k,(str,int,float,bool)): out.append(k)
    walk(code); return out
for node,keys in (("Meshing",["maxInputPoints","maxPoints","maxPointsPerVoxel","minStep",
                              "pixSizeMarginInitCoef","pixSizeMarginFinalCoef","helperPointsGridSize",
                              "estimateSpaceFromSfM","addLandmarksToTheDensePointCloud","colorizeOutput"]),
                  ("MeshFiltering",["keepLargestMeshOnly","smoothingIterations","smoothingLambda",
                                    "filteringIterations","filterLargeTrianglesFactor","filterTrianglesRatio"]),
                  ("DepthMap",["downscale"]),
                  ("Texturing",["textureSide","downscale","correctEV","workingColorSpace","outputColorSpace"])):
    p=f"/root/meshroom/lib/meshroom/nodes/aliceVision/{node}.pyc"
    if not os.path.exists(p): print(f"== {node}: 缺文件"); continue
    s=strings(p)
    print(f"== {node} 节点默认")
    for k in keys:
        try:
            i=s.index(k)
        except ValueError:
            print(f"   {k:34s} 未找到"); continue
        # value= 在 desc.Param(...) 里紧随其后的第一个非说明性常量
        tail=[x for x in s[i+1:i+14]]
        print(f"   {k:34s} -> {tail[:6]}")
