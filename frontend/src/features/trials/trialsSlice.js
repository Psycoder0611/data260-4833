import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import axios from "axios";

const API_URL = "http://localhost:8333/api/hw5/trials";


// ---------------------------------------------------------
// ASYNC THUNKS
// ---------------------------------------------------------

// GET all clinical trials
export const fetchTrials = createAsyncThunk(
  "trials/fetchTrials",
  async (_, { rejectWithValue }) => {
    try {
      const response = await axios.get(
        `${API_URL}?skip=0&limit=100`
      );

      return response.data;
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
        "Unable to fetch clinical trials"
      );
    }
  }
);


// POST a new clinical trial
export const createTrial = createAsyncThunk(
  "trials/createTrial",
  async (trialData, { rejectWithValue }) => {
    try {
      const response = await axios.post(
        API_URL,
        trialData
      );

      return response.data;
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
        "Unable to create clinical trial"
      );
    }
  }
);


// PUT update an existing clinical trial
export const editTrial = createAsyncThunk(
  "trials/editTrial",
  async ({ id, trialData }, { rejectWithValue }) => {
    try {
      const response = await axios.put(
        `${API_URL}/${id}`,
        trialData
      );

      return response.data;
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
        "Unable to update clinical trial"
      );
    }
  }
);


// DELETE a clinical trial
export const deleteTrial = createAsyncThunk(
  "trials/deleteTrial",
  async (id, { rejectWithValue }) => {
    try {
      await axios.delete(
        `${API_URL}/${id}`
      );

      return id;
    } catch (error) {
      return rejectWithValue(
        error.response?.data?.detail ||
        "Unable to delete clinical trial"
      );
    }
  }
);


// ---------------------------------------------------------
// INITIAL STATE
// ---------------------------------------------------------

const initialState = {
  records: [],
  loading: false,
  error: null,
};


// ---------------------------------------------------------
// REDUX SLICE
// ---------------------------------------------------------

const trialsSlice = createSlice({
  name: "trials",
  initialState,

  reducers: {},

  extraReducers: (builder) => {
    builder

      // FETCH
      .addCase(fetchTrials.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchTrials.fulfilled, (state, action) => {
        state.loading = false;
        state.records = action.payload;
      })
      .addCase(fetchTrials.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // CREATE
      .addCase(createTrial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(createTrial.fulfilled, (state, action) => {
        state.loading = false;
        state.records.push(action.payload);
      })
      .addCase(createTrial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // UPDATE
      .addCase(editTrial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(editTrial.fulfilled, (state, action) => {
        state.loading = false;

        const index = state.records.findIndex(
          (trial) => trial.id === action.payload.id
        );

        if (index !== -1) {
          state.records[index] = action.payload;
        }
      })
      .addCase(editTrial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      })

      // DELETE
      .addCase(deleteTrial.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(deleteTrial.fulfilled, (state, action) => {
        state.loading = false;

        state.records = state.records.filter(
          (trial) => trial.id !== action.payload
        );
      })
      .addCase(deleteTrial.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload;
      });
  },
});


export default trialsSlice.reducer;