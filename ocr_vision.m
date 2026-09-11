#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
#import <AppKit/AppKit.h>

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        for (int i = 1; i < argc; i++) {
            NSString *path = [NSString stringWithUTF8String:argv[i]];
            printf("===== %s =====\n", path.lastPathComponent.UTF8String);
            NSURL *url = [NSURL fileURLWithPath:path];
            VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] init];
            request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
            request.usesLanguageCorrection = YES;
            request.recognitionLanguages = @[@"zh-Hans", @"en-US"];
            VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithURL:url options:@{}];
            NSError *error = nil;
            [handler performRequests:@[request] error:&error];
            if (error) { printf("[OCR_ERROR] %s\n", error.localizedDescription.UTF8String); continue; }
            NSArray<VNRecognizedTextObservation *> *results = request.results;
            if (results.count == 0) {
                printf("[NO_TEXT_RESULTS]\n");
            }
            results = [results sortedArrayUsingComparator:^NSComparisonResult(VNRecognizedTextObservation *a, VNRecognizedTextObservation *b) {
                CGFloat dy = CGRectGetMidY(a.boundingBox) - CGRectGetMidY(b.boundingBox);
                if (fabs(dy) > 0.01) return dy > 0 ? NSOrderedAscending : NSOrderedDescending;
                CGFloat dx = CGRectGetMinX(a.boundingBox) - CGRectGetMinX(b.boundingBox);
                return dx < 0 ? NSOrderedAscending : NSOrderedDescending;
            }];
            for (VNRecognizedTextObservation *obs in results) {
                VNRecognizedText *text = [[obs topCandidates:1] firstObject];
                if (text) printf("%s\n", text.string.UTF8String);
            }
        }
    }
    return 0;
}
