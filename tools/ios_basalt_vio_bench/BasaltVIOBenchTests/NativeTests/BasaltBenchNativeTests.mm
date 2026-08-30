#import <XCTest/XCTest.h>

#include "BasaltBench.h"
#include <cstring>

@interface BasaltBenchNativeTests : XCTestCase
@end

@implementation BasaltBenchNativeTests

- (NSString *)bridgeSource {
    NSString *testPath = [NSString stringWithUTF8String:__FILE__];
    NSString *benchRoot = [[[testPath stringByDeletingLastPathComponent]
        stringByDeletingLastPathComponent] stringByDeletingLastPathComponent];
    NSString *sourcePath = [benchRoot
        stringByAppendingPathComponent:@"BasaltVIOBench/Native/BasaltBench.mm"];
    NSError *error = nil;
    NSString *source = [NSString stringWithContentsOfFile:sourcePath
                                                  encoding:NSUTF8StringEncoding
                                                     error:&error];
    XCTAssertNil(error);
    XCTAssertNotNil(source);
    return source;
}

- (void)testCABILifecycleRejectsNullHandles {
    basalt_bench_pose_t pose = {};
    basalt_bench_snapshot_t snapshot = {};
    XCTAssertEqual(basalt_bench_seal_inputs(nullptr),
                   BASALT_BENCH_INVALID_ARGUMENT);
    XCTAssertEqual(basalt_bench_drain(nullptr), BASALT_BENCH_INVALID_ARGUMENT);
    XCTAssertEqual(basalt_bench_stop(nullptr), BASALT_BENCH_INVALID_ARGUMENT);
    XCTAssertEqual(basalt_bench_poll_pose(nullptr, &pose),
                   BASALT_BENCH_INVALID_ARGUMENT);
    XCTAssertEqual(basalt_bench_get_snapshot(nullptr, &snapshot),
                   BASALT_BENCH_INVALID_ARGUMENT);
    basalt_bench_destroy(nullptr);
}

- (void)testStubBuildFailsClosedWithoutCreatingAHandle {
    basalt_bench_create_options_t options = {};
    options.struct_size = sizeof(options);
    options.config_path = "/missing/official-config.json";
    options.calibration_path = "/missing/official-calibration.json";
    basalt_bench_t *bench = reinterpret_cast<basalt_bench_t *>(0x1);
    basalt_bench_status_t status = basalt_bench_create(&options, &bench);
#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED
    XCTAssertEqual(status, BASALT_BENCH_IO_ERROR);
#else
    XCTAssertEqual(status, BASALT_BENCH_BACKEND_UNAVAILABLE);
#endif
    XCTAssertEqual(bench, nullptr);
}

- (void)testOfficialFloatIMUFactoryExpansionAndInitializationOrderAreFrozen {
    NSString *source = [self bridgeSource];
    NSRange factory = [source rangeOfString:
        @"std::make_shared<basalt::SqrtKeypointVioEstimator<float>>("];
    NSRange flags = [source rangeOfString:
        @"use_imu=true/use_double=false"];
    NSRange initialize = [source rangeOfString:
        @"bench->estimator->initialize(Eigen::Vector3d::Zero()"];
    NSRange wiring = [source rangeOfString:
        @"&bench->estimator->vision_data_queue"];
    XCTAssertNotEqual(factory.location, NSNotFound);
    XCTAssertNotEqual(flags.location, NSNotFound);
    XCTAssertNotEqual(initialize.location, NSNotFound);
    XCTAssertNotEqual(wiring.location, NSNotFound);
    XCTAssertLessThan(factory.location, initialize.location);
    XCTAssertLessThan(initialize.location, wiring.location);
}

- (void)testInputConversionMonotonicityAndFiniteOutputGuardsArePresent {
    NSString *source = [self bridgeSource];
    XCTAssertTrue([source containsString:
        @"static_cast<uint16_t>(source[col]) << 8"]);
    XCTAssertTrue([source containsString:
        @"timestamp_ns <= bench->last_camera_timestamp_ns"]);
    XCTAssertTrue([source containsString:
        @"timestamp_ns <= bench->last_imu_timestamp_ns"]);
    XCTAssertTrue([source containsString:@"pose_is_finite(*state)"]);
}

- (void)testSnapshotExportsOfficialQueueCapacityForLosslessReplayBackpressure {
    basalt_bench_snapshot_t snapshot = {};
    XCTAssertEqual(snapshot.optical_flow_input_queue_capacity, 0u);
    XCTAssertEqual(snapshot.vio_imu_queue_capacity, 0u);
    NSString *source = [self bridgeSource];
    XCTAssertTrue([source containsString:@"input_queue.capacity()"]);
    XCTAssertTrue([source containsString:@"imu_data_queue.capacity()"]);
}

- (void)testShutdownUsesExactEOFSentinelsAndOfficialJoinOrder {
    NSString *source = [self bridgeSource];
    NSRange sealFunction = [source rangeOfString:
        @"basalt_bench_status_t seal_locked"];
    NSRange imageEOF = [source rangeOfString:
        @"bench->optical_flow->input_queue.push(nullptr)"
                                  options:0
                                    range:NSMakeRange(sealFunction.location,
                                        source.length - sealFunction.location)];
    NSRange imuEOF = [source rangeOfString:
        @"bench->estimator->imu_data_queue.push(nullptr)"
                                  options:0
                                    range:NSMakeRange(sealFunction.location,
                                        source.length - sealFunction.location)];
    NSRange drainFunction = [source rangeOfString:
        @"basalt_bench_status_t basalt_bench_drain"];
    NSRange join = [source rangeOfString:@"bench->estimator->maybe_join()"
                                options:0
                                  range:NSMakeRange(drainFunction.location,
                                      source.length - drainFunction.location)];
    NSRange drain = [source rangeOfString:
        @"bench->estimator->drain_input_queues()"
                                 options:0
                                   range:NSMakeRange(drainFunction.location,
                                       source.length - drainFunction.location)];
    XCTAssertNotEqual(imageEOF.location, NSNotFound);
    XCTAssertNotEqual(imuEOF.location, NSNotFound);
    XCTAssertNotEqual(join.location, NSNotFound);
    XCTAssertNotEqual(drain.location, NSNotFound);
    XCTAssertLessThan(join.location, drain.location);
}

- (void)testEveryStatusHasAStableName {
    for (int raw = BASALT_BENCH_OK; raw <= BASALT_BENCH_INTERNAL_ERROR; ++raw) {
        const char *name = basalt_bench_status_name(
            static_cast<basalt_bench_status_t>(raw));
        XCTAssertNotEqual(strcmp(name, "unknown"), 0);
    }
}

@end
