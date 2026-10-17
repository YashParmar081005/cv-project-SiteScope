// Form checks before sending (the server validates everything again). Pure functions, tested with `npm test`.

export const CONSTRUCTION_TYPES = {
  residential_building: "Residential building",
  commercial_building: "Commercial building",
  bridge: "Bridge",
  road: "Road",
  rail: "Rail infrastructure",
  other: "Other construction",
};
export const ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp", "image/bmp"];
const EMAIL_RE = /^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$/;

export function validateProject(p) {
  const errors = {};
  if (!p.name || p.name.trim().length < 3) errors.name = "Name needs at least 3 characters.";
  else if (p.name.length > 120) errors.name = "Name is too long (max 120).";
  if (!(p.construction_type in CONSTRUCTION_TYPES)) errors.construction_type = "Choose a construction type.";
  if (!p.planned_start_date) errors.planned_start_date = "Start date is required.";
  if (!p.target_completion_date) errors.target_completion_date = "Planned finish date is required.";
  else if (p.planned_start_date && p.target_completion_date <= p.planned_start_date) {
    errors.target_completion_date = "Planned finish must be after the start date.";
  }
  return errors;
}

export function validateUpload({ file, captureDate }, { maxMb = 15, today }) {
  const errors = {};
  if (!file) errors.file = "Choose a photo.";
  else if (!ALLOWED_IMAGE_TYPES.includes(file.type)) errors.file = "Use a JPEG, PNG, WebP or BMP image.";
  else if (file.size > maxMb * 1024 * 1024) errors.file = `Photo is larger than ${maxMb} MB.`;
  else if (file.size === 0) errors.file = "The file is empty.";
  if (!captureDate) errors.capture_date = "Date taken is required.";
  else if (today && captureDate > today) errors.capture_date = "Date taken cannot be in the future.";
  else if (captureDate < "1990-01-01") errors.capture_date = "Date taken is too early.";
  return errors;
}

export function validateCredentials({ email, password, name }, mode = "login") {
  const errors = {};
  if (!EMAIL_RE.test(email || "")) errors.email = "Enter a valid email address.";
  if (mode === "register") {
    if (!name || name.trim().length < 2) errors.name = "Enter your name.";
    if (!password || password.length < 8) errors.password = "Use at least 8 characters.";
  } else if (!password) errors.password = "Enter your password.";
  return errors;
}
