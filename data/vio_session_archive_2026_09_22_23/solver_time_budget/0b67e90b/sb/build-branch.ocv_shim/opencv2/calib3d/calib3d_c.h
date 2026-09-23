/* shim: OpenCV 5 has no calib3d_c.h; the tree only needs CV_EPNP (OpenCV 4.0.1: CV_EPNP=1 == cv::SOLVEPNP_EPNP). */
#ifndef PW_CALIB3D_C_SHIM_H
#define PW_CALIB3D_C_SHIM_H
#include <opencv2/calib3d.hpp>
#ifndef CV_EPNP
#define CV_EPNP cv::SOLVEPNP_EPNP
#endif
#endif
