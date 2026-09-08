// CPU 参考探针:复刻 XRSLAM OpenCvImage 的检测链(cornerHarris block3 ksize3 k0.04 → goodFeaturesToTrack quality1e-3 minDist20),
// 并把中间量(Dx,Dy,eig)与角点表导出,供 GPU 版逐元素对拍。参考语义=OpenCV 4.0.1 cornerEigenValsVecs;这里用 brew OpenCV 迭代,最终以设备 4.0.1 为准。
#include <opencv2/opencv.hpp>
#include <cstdio>
#include <chrono>
static void dump(const cv::Mat& m, const std::string& p){ FILE* f=fopen(p.c_str(),"wb"); fwrite(m.data,1,m.total()*m.elemSize(),f); fclose(f); }
int main(int argc,char**argv){
  if(argc<3){fprintf(stderr,"usage: gftt_cpu_ref <png> <outdir> [W H]\n");return 1;}
  cv::Mat img=cv::imread(argv[1],cv::IMREAD_GRAYSCALE); std::string out=argv[2];
  if(argc>=5) cv::resize(img,img,cv::Size(atoi(argv[3]),atoi(argv[4])),0,0,cv::INTER_LINEAR);
  CV_Assert(img.type()==CV_8UC1);
  const int block=3, ksize=3; const double k=0.04, quality=1e-3, minDist=20; const int maxCorners=200;
  double scale=(double)(1<<(ksize-1))*block; scale*=255.0; scale=1.0/scale;   // corner.cpp 4.0.1 语义(8U)
  cv::Mat Dx,Dy; cv::Sobel(img,Dx,CV_32F,1,0,ksize,scale,0,cv::BORDER_DEFAULT); cv::Sobel(img,Dy,CV_32F,0,1,ksize,scale,0,cv::BORDER_DEFAULT);
  auto t0=std::chrono::steady_clock::now();
  cv::Mat eig; cv::cornerHarris(img,eig,block,ksize,k,cv::BORDER_DEFAULT);
  auto t1=std::chrono::steady_clock::now();
  std::vector<cv::Point2f> corners; cv::goodFeaturesToTrack(img,corners,maxCorners,quality,minDist,cv::noArray(),block,ksize,true,k);
  auto t2=std::chrono::steady_clock::now();
  double mx; cv::minMaxLoc(eig,nullptr,&mx);
  dump(Dx,out+"/dx.f32"); dump(Dy,out+"/dy.f32"); dump(eig,out+"/eig.f32"); dump(img,out+"/img.u8");
  FILE* f=fopen((out+"/corners_cpu.txt").c_str(),"w"); for(auto&c:corners) fprintf(f,"%.3f %.3f %.9g\n",c.x,c.y,eig.at<float>((int)c.y,(int)c.x)); fclose(f);
  printf("%dx%d maxEig=%.9g thr=%.9g corners=%zu harris=%.2fms gftt(total)=%.2fms\n",img.cols,img.rows,mx,mx*quality,corners.size(),
    std::chrono::duration<double,std::milli>(t1-t0).count(), std::chrono::duration<double,std::milli>(t2-t1).count());
  return 0; }
