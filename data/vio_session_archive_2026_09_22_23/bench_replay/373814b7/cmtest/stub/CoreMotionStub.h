#import <Foundation/Foundation.h>
typedef struct { double x; double y; double z; } CMRotationRate;
@interface CMLogItem : NSObject
@property(readonly, nonatomic) NSTimeInterval timestamp;
@end
@interface CMGyroData : CMLogItem
@property(readonly, nonatomic) CMRotationRate rotationRate;
@end
@interface CMMotionManager : NSObject
@property(readonly, nonatomic, getter=isGyroAvailable) BOOL gyroAvailable;
@end
