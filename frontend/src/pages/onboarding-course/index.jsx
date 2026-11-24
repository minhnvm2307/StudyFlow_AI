import { ArrowLeft, Loader2, Sparkles } from "lucide-react";
import { Button, Card } from "../../components/common.jsx";
import {
  OnboardingTopBar,
  PreviewCard,
  Stepper
} from "./components.jsx";
import { StepDocuments, StepFour, StepOne, StepTwo } from "./steps.jsx";
import { useOnboardingCourse } from "./useOnboardingCourse.js";

export default function OnboardingCoursePage() {
  const onboarding = useOnboardingCourse();
  const {
    currentStep,
    dirty,
    errors,
    files,
    form,
    isLastStep,
    isSubmitting,
    setFiles,
    setSyllabusFile,
    setSkippedSources,
    skippedSources,
    sourceCount,
    submitError,
    syllabusFile,
    addAvailabilityWindow,
    addClassMeeting,
    handleBack,
    handleCancel,
    handleNext,
    handleSubmit,
    removeAvailabilityWindow,
    removeClassMeeting,
    toggleAvailabilityDay,
    updateAvailabilityWindow,
    updateClassMeeting,
    update
  } = onboarding;

  return (
    <div className="onboarding-shell">
      <OnboardingTopBar dirty={dirty} />
      <main className="onboarding-container">
        <div className="onboarding-hero">
          <h1>Tạo môn học mới</h1>
          <p>Thiết lập môn học để StudyFlow tạo lịch học, quiz, flashcard và chatbot theo tài liệu của bạn.</p>
        </div>
        <Stepper currentStep={currentStep} />
        <div className="onboarding-layout">
          <Card className="course-form-card">
            {currentStep === 0 ? <StepOne form={form} update={update} errors={errors} /> : null}
            {currentStep === 1 ? (
              <StepTwo
                form={form}
                update={update}
                addAvailabilityWindow={addAvailabilityWindow}
                addClassMeeting={addClassMeeting}
                removeAvailabilityWindow={removeAvailabilityWindow}
                removeClassMeeting={removeClassMeeting}
                toggleAvailabilityDay={toggleAvailabilityDay}
                updateAvailabilityWindow={updateAvailabilityWindow}
                updateClassMeeting={updateClassMeeting}
                errors={errors}
              />
            ) : null}
            {currentStep === 2 ? (
              <StepDocuments
                form={form}
                update={update}
                errors={errors}
                files={files}
                setFiles={setFiles}
                skippedSources={skippedSources}
                setSkippedSources={setSkippedSources}
                syllabusFile={syllabusFile}
                setSyllabusFile={setSyllabusFile}
              />
            ) : null}
            {currentStep === 3 ? <StepFour form={form} sourceCount={sourceCount} skippedSources={skippedSources} /> : null}

            {submitError ? <div className="onboarding-error">{submitError}</div> : null}

            <div className="onboarding-footer">
              <Button variant="secondary" onClick={currentStep === 0 ? handleCancel : handleBack} icon={currentStep === 0 ? undefined : ArrowLeft} disabled={isSubmitting}>
                {currentStep === 0 ? "Hủy" : "Quay lại"}
              </Button>
              {!isLastStep ? (
                <Button variant="primary" onClick={handleNext}>Tiếp tục</Button>
              ) : (
                <Button variant="primary" onClick={handleSubmit} icon={isSubmitting ? Loader2 : Sparkles} disabled={isSubmitting}>
                  {isSubmitting ? "Đang tạo kế hoạch..." : "Tạo kế hoạch học"}
                </Button>
              )}
            </div>
          </Card>
          <PreviewCard form={form} sourceCount={sourceCount} />
        </div>
      </main>
    </div>
  );
}
