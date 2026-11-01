// Public site settings, read at build time from VITE_* variables (see .env.example).
// Unset values stay empty and are shown as "to be announced" rather than invented.
const env = import.meta.env;

export const SITE = {
  name: 'CMGI Apps',
  organisation: env.VITE_ORGANISATION_NAME || 'CMGI',
  contact: {
    email: env.VITE_CONTACT_EMAIL || '',
    phone: env.VITE_CONTACT_PHONE || '',
    address: env.VITE_CONTACT_ADDRESS || '',
  },
};
