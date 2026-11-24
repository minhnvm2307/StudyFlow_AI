import { Flame, School } from 'lucide-react';

export const steps = ['Thông tin môn', 'Mục tiêu & lịch', 'Tài liệu', 'Xác nhận'];

export const modes = [
  { id: 'continuous', title: 'Học kỳ liên tục', icon: School, description: 'Theo dõi tiến độ và ôn tập đều theo lịch trên lớp.', helper: 'Phù hợp khi bạn đang học môn này trong học kỳ.' },
  { id: 'exam_sprint', title: 'Ôn thi tăng tốc', icon: Flame, description: 'Ưu tiên phần quan trọng khi ngày thi đang đến gần.', helper: 'Phù hợp khi bạn cần ôn trong thời gian ngắn.' }
];

export const priorities = [
  { id: 'low', label: 'Thấp' },
  { id: 'medium', label: 'Trung bình' },
  { id: 'high', label: 'Cao' }
];
export const weekdays = [
  { key: 'Mon', label: 'T2' },
  { key: 'Tue', label: 'T3' },
  { key: 'Wed', label: 'T4' },
  { key: 'Thu', label: 'T5' },
  { key: 'Fri', label: 'T6' },
  { key: 'Sat', label: 'T7' },
  { key: 'Sun', label: 'CN' }
];
export const weekdayLabels = Object.fromEntries(weekdays.map((day) => [day.key, day.label]));
export const initialForm = {
  name: '',
  mode: 'continuous',
  priority: 'high',
  examDate: '',
  targetScore: '85',
  sessionMinutes: '30',
  availability: ['T2', 'T4', 'T6'],
  startTime: '19:00',
  availabilityWindows: [
    { day: 'Mon', start: '19:00', end: '19:30' },
    { day: 'Wed', start: '19:00', end: '19:30' },
    { day: 'Fri', start: '19:00', end: '19:30' }
  ],
  semesterStartDate: '',
  semesterEndDate: '',
  classMeetings: [
    { day: 'Mon', start: '08:00', end: '09:30' }
  ],
  syllabusMode: 'upload',
  syllabusText: '',
  currentWeek: '1',
  currentLessonNumber: '1',
  wantsDiagnostic: true,
  websiteUrl: '',
  pastedText: ''
};
