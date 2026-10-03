import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";

import { createTrial } from "../features/trials/trialsSlice";


function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { loading, error } = useSelector(
    (state) => state.trials
  );

  const [trialTitle, setTrialTitle] = useState("");
  const [trialCode, setTrialCode] = useState("");
  const [participantCapacity, setParticipantCapacity] =
    useState(100);
  const [organizationId, setOrganizationId] = useState("");


  const handleSubmit = async (event) => {
    event.preventDefault();

    const trialData = {
      trialTitle: trialTitle.trim(),
      trial_code: trialCode.trim(),
      participant_capacity: Number(participantCapacity),
      organization_id: Number(organizationId),
    };

    try {
      await dispatch(
        createTrial(trialData)
      ).unwrap();

      navigate("/");
    } catch {
      // Redux stores the API error in state.
    }
  };


  return (
    <div className="page-container">
      <h1>Add Clinical Trial</h1>

      <form onSubmit={handleSubmit}>

        <div>
          <label htmlFor="trialTitle">
            Trial Title
          </label>

          <input
            id="trialTitle"
            type="text"
            value={trialTitle}
            onChange={(event) =>
              setTrialTitle(event.target.value)
            }
            placeholder="Enter trial title"
            required
          />
        </div>


        <div>
          <label htmlFor="trialCode">
            Trial Code
          </label>

          <input
            id="trialCode"
            type="text"
            value={trialCode}
            onChange={(event) =>
              setTrialCode(event.target.value)
            }
            placeholder="Example: CT-2026-003"
            required
          />
        </div>


        <div>
          <label htmlFor="participantCapacity">
            Participant Capacity
          </label>

          <input
            id="participantCapacity"
            type="number"
            min="1"
            value={participantCapacity}
            onChange={(event) =>
              setParticipantCapacity(event.target.value)
            }
            required
          />
        </div>


        <div>
          <label htmlFor="organizationId">
            Organization ID
          </label>

          <input
            id="organizationId"
            type="number"
            min="1"
            value={organizationId}
            onChange={(event) =>
              setOrganizationId(event.target.value)
            }
            placeholder="Example: 2"
            required
          />
        </div>


        <button type="submit" disabled={loading}>
          {loading ? "Creating..." : "Add Clinical Trial"}
        </button>

      </form>

      {error && (
        <p className="error-message">
          {error}
        </p>
      )}
    </div>
  );
}


export default CreateRecord;