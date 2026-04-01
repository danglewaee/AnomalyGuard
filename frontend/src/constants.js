export const VN_STATIONS = [
  { id: "mekong-can-tho", label: "Can Tho (Mekong)" },
  { id: "saigon-thu-duc", label: "Thu Duc (Saigon River)" },
  { id: "red-river-ha-noi", label: "Long Bien (Red River)" },
];

export const EMPTY_DEVICE_CONTROL = {
  direction: 0,
  pump: false,
  isFeeding: false,
  weight: 100,
  hour: 0,
  minute: 0,
};

export const DIRECTION_OPTIONS = [
  { value: 0, label: "Stop" },
  { value: 1, label: "Forward" },
  { value: 2, label: "Reverse" },
  { value: 3, label: "Left" },
  { value: 4, label: "Right" },
];

export const TIME_WINDOW_OPTIONS = [
  { value: 60, label: "Last 60 minutes" },
  { value: 180, label: "Last 3 hours" },
  { value: 720, label: "Last 12 hours" },
  { value: 1440, label: "Last 24 hours" },
  { value: 4320, label: "Last 3 days" },
  { value: 10080, label: "Last 7 days" },
];

export const COMMUNITY_WINDOW_OPTIONS = [
  { value: 180, label: "3 hours" },
  { value: 720, label: "12 hours" },
  { value: 1440, label: "24 hours" },
  { value: 4320, label: "3 days" },
];
