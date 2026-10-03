import { configureStore } from "@reduxjs/toolkit";
import trialsReducer from "../features/trials/trialsSlice";

export const store = configureStore({
  reducer: {
    trials: trialsReducer,
  },
});